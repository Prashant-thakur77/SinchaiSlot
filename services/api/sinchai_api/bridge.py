"""MQTT bridge: publishes each plan for the external edge controller (pump P2 runs the full
Modbus + MQTT path against the drive simulator) and stores its telemetry. Active only when
MQTT_HOST is set (docker compose)."""

from __future__ import annotations

import json
import logging
from datetime import datetime

from . import db
from .settings import settings

_client = None
log = logging.getLogger("sinchai.bridge")


def start() -> None:
    global _client
    if not settings().mqtt_host or _client is not None:
        return
    import paho.mqtt.client as mqtt

    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="sinchai-api")

    def on_msg(cl, ud, m):
        # Never let an exception escape: in paho-mqtt 2 it would stop the network loop for good.
        try:
            data = json.loads(m.payload)
            pump = m.topic.split("/")[1]
            with db.session() as s:
                s.add(db.Telemetry(ts=datetime.utcnow(), pump_id=pump, data=data))
                s.commit()
        except Exception as e:  # noqa: BLE001
            log.warning("telemetry not stored: %s", e)

    c.on_message = on_msg
    c.on_connect = lambda cl, *a, **k: cl.subscribe("sinchai/+/telemetry", qos=0)
    c.connect_async(settings().mqtt_host, settings().mqtt_port, keepalive=30)
    c.loop_start()
    _client = c


def publish_plan(pump_id: str, plan: dict) -> None:
    if _client is not None:
        _client.publish(f"sinchai/{pump_id}/plan", json.dumps(plan), qos=1, retain=True)
