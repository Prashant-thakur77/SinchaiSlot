// SinchaiSlot Edge firmware: same protocol as services/edge/sinchai_edge (docs/edge-protocol.md).
// Holds the plan in NVS, runs paid slots on the Altivar drive over Modbus RTU, verifies unlock codes
// offline, meters water from drive telemetry, enforces budget and dry-run cut-off, queues uplink
// messages while offline.
#include <Arduino.h>
#include <ArduinoJson.h>
#include <ModbusMaster.h>
#include <Preferences.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <mbedtls/md.h>
#include <time.h>

#include "config.h"
#include "pump_curve.h"

static ModbusMaster drive;
static WiFiClient net;
static PubSubClient mqtt(net);
static Preferences nvs;
static JsonDocument plan;
static String secret;
static long lastCounter = -1;
static float budgetUsed = 0, deliveredActive = 0, kwhActive = 0;
static String activeBooking = "";
static float underloadS = 0;
static bool tripped = false;

static const int OUTBOX_MAX = 256;
static String outboxTopic[OUTBOX_MAX], outboxMsg[OUTBOX_MAX];
static int outHead = 0, outCount = 0;

static void preTx() { digitalWrite(RS485_DE_PIN, HIGH); }
static void postTx() { digitalWrite(RS485_DE_PIN, LOW); }

static void enqueue(const String &kind, JsonDocument &doc) {
  doc["pump_id"] = SINCHAI_PUMP_ID;
  String s;
  serializeJson(doc, s);
  int i = (outHead + outCount) % OUTBOX_MAX;
  outboxTopic[i] = String("sinchai/") + SINCHAI_PUMP_ID + "/" + kind;
  outboxMsg[i] = s;
  if (outCount < OUTBOX_MAX) outCount++; else outHead = (outHead + 1) % OUTBOX_MAX;
}

static void flush() {
  while (outCount > 0 && mqtt.connected()) {
    if (!mqtt.publish(outboxTopic[outHead].c_str(), outboxMsg[outHead].c_str())) break;
    outHead = (outHead + 1) % OUTBOX_MAX;
    outCount--;
  }
}

static bool writeReg(uint16_t reg, uint16_t v) { return drive.writeSingleRegister(reg, v) == drive.ku8MBSuccess; }
static bool readReg(uint16_t reg, uint16_t &v) {
  if (drive.readHoldingRegisters(reg, 1) != drive.ku8MBSuccess) return false;
  v = drive.getResponseBuffer(0);
  return true;
}

static void driveStart() {
  writeReg(REG_CMD, CMD_SHUTDOWN);
  delay(100);
  writeReg(REG_LFR, 500);  // 50.0 Hz reference, MPPT limits actual speed
  writeReg(REG_CMD, CMD_ENABLE_OP);
}
static void driveStop() { writeReg(REG_CMD, CMD_SWITCH_ON); }

// 9-digit unlock code, identical to sinchai_edge.controller.unlock_code
static String unlockCode(const String &booking, float m3, long counter) {
  String msg = String(SINCHAI_PUMP_ID) + "|" + booking + "|" + String((long)lroundf(m3 * 10)) + "|" + String(counter);
  uint8_t out[32];
  mbedtls_md_context_t ctx;
  mbedtls_md_init(&ctx);
  mbedtls_md_setup(&ctx, mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), 1);
  mbedtls_md_hmac_starts(&ctx, (const unsigned char *)secret.c_str(), secret.length());
  mbedtls_md_hmac_update(&ctx, (const unsigned char *)msg.c_str(), msg.length());
  mbedtls_md_hmac_finish(&ctx, out);
  mbedtls_md_free(&ctx);
  uint64_t v = 0;
  for (int i = 0; i < 8; i++) v = (v << 8) | out[i];
  char buf[10];
  snprintf(buf, sizeof(buf), "%09llu", (unsigned long long)(v % 1000000000ULL));
  return String(buf);
}

static void persist() {
  String s;
  serializeJson(plan, s);
  nvs.putString("plan", s);
  nvs.putLong("counter", lastCounter);
  nvs.putFloat("budgetUsed", budgetUsed);
}

static void onMessage(char *topic, byte *payload, unsigned int len) {
  JsonDocument doc;
  if (deserializeJson(doc, payload, len)) return;
  String t(topic);
  if (t.endsWith("/plan")) {
    if (!plan.isNull() && doc["version"].as<int>() <= plan["version"].as<int>()) return;
    plan = doc;
    budgetUsed = 0;
    persist();
    JsonDocument ev; ev["type"] = "plan_accepted"; ev["version"] = plan["version"]; enqueue("event", ev);
  } else if (t.endsWith("/cmd")) {
    String type = doc["type"].as<String>();
    if (type == "unlock") {
      String b = doc["booking_id"].as<String>(), code = doc["code"].as<String>();
      for (JsonObject s : plan["slots"].as<JsonArray>()) {
        if (s["booking_id"].as<String>() != b) continue;
        for (long c = lastCounter + 1; c < lastCounter + 50; c++) {
          if (unlockCode(b, s["m3"].as<float>(), c) == code) {
            s["paid"] = true; lastCounter = c; persist();
            JsonDocument ev; ev["type"] = "unlocked"; ev["booking_id"] = b; enqueue("event", ev);
            return;
          }
        }
      }
    } else if (type == "stop") {
      driveStop();
    } else if (type == "reset_fault") {
      writeReg(REG_CMD, 0); writeReg(REG_CMD, CMD_FAULT_RESET); tripped = false;
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(RS485_DE_PIN, OUTPUT);
  postTx();
  Serial2.begin(MODBUS_BAUD, MODBUS_CONFIG);
  drive.begin(DRIVE_ADDR, Serial2);
  drive.preTransmission(preTx);
  drive.postTransmission(postTx);
  nvs.begin("sinchai", false);
  secret = nvs.getString("secret", "");
  lastCounter = nvs.getLong("counter", -1);
  budgetUsed = nvs.getFloat("budgetUsed", 0);
  String p = nvs.getString("plan", "");
  if (p.length()) deserializeJson(plan, p);
  WiFi.begin(nvs.getString("ssid", "").c_str(), nvs.getString("wpa", "").c_str());
  mqtt.setServer(nvs.getString("broker", "").c_str(), 1883);
  mqtt.setCallback(onMessage);
  configTime(19800, 0, "pool.ntp.org");  // IST
}

void loop() {
  static uint32_t last = 0;
  if (WiFi.status() == WL_CONNECTED && !mqtt.connected()) {
    String id = String("edge-") + SINCHAI_PUMP_ID;
    if (mqtt.connect(id.c_str())) {
      mqtt.subscribe((String("sinchai/") + SINCHAI_PUMP_ID + "/plan").c_str(), 1);
      mqtt.subscribe((String("sinchai/") + SINCHAI_PUMP_ID + "/cmd").c_str(), 1);
    }
  }
  mqtt.loop();
  if (millis() - last < CONTROL_PERIOD_MS) return;
  float dtH = (millis() - last) / 3600000.0f;
  last = millis();

  uint16_t eta = 0, rfr = 0, opr = 0, lft = 0;
  bool ok = readReg(REG_ETA, eta) && readReg(REG_RFR, rfr) && readReg(REG_OPR, opr) && readReg(REG_LFT, lft);
  float hz = rfr / 10.0f, kw = (int16_t)opr / 100.0f * PUMP_RATED_KW;
  bool running = ok && ((eta & 0x6F) == 0x27);

  char now[17];
  struct tm tmv;
  if (!getLocalTime(&tmv, 10)) return;  // no clock yet
  strftime(now, sizeof(now), "%Y-%m-%dT%H:%M", &tmv);

  if (running && activeBooking.length()) {
    float q = flowAtSpeed(hz / 50.0f);
    float expected = powerAtSpeed(hz / 50.0f);
    if (expected > 0.3f && kw < 0.6f * expected) underloadS += dtH * 3600; else underloadS = 0;
    if (underloadS > 20) {
      tripped = true; driveStop();
      JsonDocument ev; ev["type"] = "dry_run_cutoff"; ev["booking_id"] = activeBooking; enqueue("event", ev);
    } else {
      deliveredActive += q * dtH; kwhActive += kw * dtH; budgetUsed += q * dtH;
    }
  }
  if (lft != 0 && !tripped) {
    tripped = true;
    JsonDocument ev; ev["type"] = "drive_fault"; ev["lft"] = lft; enqueue("event", ev);
  }

  JsonObject slot;
  for (JsonObject s : plan["slots"].as<JsonArray>())
    if (strcmp(s["start"] | "", now) <= 0 && strcmp(now, s["end"] | "") < 0) slot = s;
  bool want = !slot.isNull() && String(slot["kind"] | "") == "water" && (slot["paid"] | false) && !tripped &&
              lft == 0 && budgetUsed < plan["budget_remaining_m3"].as<float>() && deliveredActive < slot["m3"].as<float>();
  String b = slot.isNull() ? "" : slot["booking_id"].as<String>();

  if (activeBooking.length() && (!want || b != activeBooking)) {
    driveStop();
    JsonDocument ev; ev["type"] = "slot_completed"; ev["booking_id"] = activeBooking; ev["m3"] = deliveredActive;
    ev["kwh"] = kwhActive; ev["method"] = "drive-estimate"; enqueue("event", ev);
    activeBooking = ""; deliveredActive = 0; kwhActive = 0;
    persist();
  }
  if (want && !activeBooking.length()) {
    activeBooking = b;
    driveStart();
    JsonDocument ev; ev["type"] = "slot_started"; ev["booking_id"] = b; enqueue("event", ev);
  }
  JsonDocument tel;
  tel["ts"] = now; tel["eta"] = eta; tel["freq_hz"] = hz; tel["power_kw"] = kw; tel["lft"] = lft;
  tel["active_booking"] = activeBooking;
  enqueue("telemetry", tel);
  flush();
}
