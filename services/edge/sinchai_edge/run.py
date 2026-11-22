"""Run the edge controller as a process: Modbus to the (simulated) drive, MQTT to the platform.

    uv run python -m sinchai_edge.run --pump P1 --drive tcp://localhost:5020 --mqtt localhost:1883
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import datetime
from pathlib import Path

from sinchai_devices.adapter import AltivarModbusAdapter

from .controller import EdgeController, MqttUplink


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pump", default=os.getenv("PUMP_ID", "P1"))
    ap.add_argument("--drive", default=os.getenv("DRIVE_URL", "tcp://localhost:5020"))
    ap.add_argument("--mqtt", default=os.getenv("MQTT_HOST", "localhost:1883"))
    ap.add_argument("--state-dir", default=os.getenv("EDGE_STATE_DIR", "/tmp/sinchai-edge"))
    ap.add_argument("--period", type=float, default=2.0)
    a = ap.parse_args()

    host, port = a.drive.removeprefix("tcp://").split(":")
    drive = None
    while drive is None:
        try:
            drive = AltivarModbusAdapter(host, int(port))
        except ConnectionError:
            print("waiting for drive...", flush=True)
            time.sleep(2)
    mh, mp = a.mqtt.split(":")
    up = MqttUplink(mh, int(mp), client_id=f"edge-{a.pump}")
    secret = os.getenv("EDGE_SECRET", "dev-only-secret").encode()
    ec = EdgeController(a.pump, drive, secret, up, state_dir=Path(a.state_dir))
    ec.load_cached_plan()
    up.subscribe(f"sinchai/{a.pump}/plan", ec.receive_plan)

    def on_cmd(msg: dict) -> None:
        if msg.get("type") == "unlock":
            ec.enter_code(msg["booking_id"], msg["code"])
        elif msg.get("type") == "stop":
            drive.stop()
        elif msg.get("type") == "reset_fault":
            drive.reset_fault()
            ec.tripped = None

    up.subscribe(f"sinchai/{a.pump}/cmd", on_cmd)
    print(f"edge {a.pump} running", flush=True)
    while True:
        try:
            ec.step(datetime.now())
        except Exception as e:  # keep the field device alive; report and continue
            print(f"step error: {e}", flush=True)
        time.sleep(a.period)


if __name__ == "__main__":
    main()
