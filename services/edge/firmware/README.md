# SinchaiSlot Edge firmware (ESP32)

PlatformIO project implementing the same protocol as the Python edge simulator
(`../sinchai_edge`, see `docs/edge-protocol.md`): Modbus RTU over RS-485 to the Altivar Solar drive,
MQTT uplink, offline plan, unlock codes, drive-as-meter, budget and dry-run cut-off.

Build: `pio run` (needs PlatformIO). Provision NVS keys `secret`, `ssid`, `wpa`, `broker` at install.
Hardware: ESP32 DevKit + MAX3485 transceiver on Serial2, DE/RE on GPIO 4, to the drive's RJ45 Modbus port.

Status: not yet compiled in CI and not yet run on hardware. Register addresses come only
from the verified register map.
