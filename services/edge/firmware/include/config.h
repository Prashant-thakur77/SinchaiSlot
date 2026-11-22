#pragma once
// Site configuration. Secrets are provisioned into NVS at install time, not compiled in.
#ifndef SINCHAI_PUMP_ID
#define SINCHAI_PUMP_ID "P1"
#endif
#define MODBUS_BAUD 19200          // NVE41308 p.32: factory 19.2 kbps
#define MODBUS_CONFIG SERIAL_8E1   // NVE41308 p.33: factory 8E1
#define DRIVE_ADDR 1               // ADD (6001) must be set 1..247 on the drive (factory OFF)
#define CONTROL_PERIOD_MS 2000

// Verified Altivar ATV320 registers (docs/schneider/register_map.yaml)
#define REG_CMD 8501
#define REG_LFR 8502
#define REG_ETA 3201
#define REG_RFR 3202
#define REG_LCR 3204
#define REG_THD 3209
#define REG_OPR 3211
#define REG_APH 3230
#define REG_UNT 3234
#define REG_LFT 7121

#define CMD_SHUTDOWN 0x0006
#define CMD_SWITCH_ON 0x0007
#define CMD_ENABLE_OP 0x000F
#define CMD_FAULT_RESET 0x0080
