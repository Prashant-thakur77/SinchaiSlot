# Edge protocol (MQTT)

One protocol for the Python edge simulator (`services/edge/sinchai_edge`) and the ESP32 firmware
(`services/edge/firmware`). JSON payloads, QoS 1, UTF-8.

| Topic | Direction | Retained | Payload |
|---|---|---|---|
| `sinchai/<pump>/plan` | cloud → edge | yes | `{pump_id, version, budget_remaining_m3, slots: [{start, end, kind, booking_id, m3, paid}]}` |
| `sinchai/<pump>/cmd` | cloud → edge | no | `{type: "unlock", booking_id, code}` · `{type: "stop"}` · `{type: "reset_fault"}` |
| `sinchai/<pump>/telemetry` | edge → cloud | no | drive telemetry (state, freq_hz, power_kw, energy_kwh, fault, ...) + `active_booking`, `budget_left_m3` |
| `sinchai/<pump>/event` | edge → cloud | no | `plan_accepted`, `unlocked`, `unlock_rejected`, `slot_started`, `slot_completed {m3, kwh, method}`, `drive_fault {fault, lft}`, `dry_run_cutoff`, `budget_cutoff` |

Rules
- `start`/`end` are local ISO times to the minute; a slot runs only if `kind = water`, `paid = true`
  (or unlocked on the device), no fault, budget left, and delivered < `m3`.
- A plan with a version lower than or equal to the held plan is ignored. Payment flags already
  granted on the device are kept across plan versions.
- The edge keeps working with no uplink: plan, unlock counter, delivered volumes and budget use are
  persisted to flash/disk; telemetry and events queue in an outbox and flush in order on reconnect.

Unlock codes
- `code = HMAC-SHA256(secret, "<pump>|<booking>|<m3 x 10>|<counter>")`, first 8 bytes as a big-endian
  integer, mod 10^9, zero-padded to 9 digits.
- The device accepts counters `last+1 .. last+49` and then stores the accepted counter: each code
  works once, and old codes cannot be replayed.

Drive side
- Modbus RTU (RS-485, 19200 8E1, NVE41308 p.32-33) or TCP gateway to the Altivar Solar ATV320, using
  only registers marked verified in `docs/schneider/register_map.yaml`.
- Start: CMD 0x0006 → wait ETA&0x6F = 0x21 → LFR → CMD 0x000F → wait 0x27. Stop: CMD 0x0007.
  Fault reset: CMD 0x0000 then 0x0080 (NVE41308 p.46, p.51-52).
