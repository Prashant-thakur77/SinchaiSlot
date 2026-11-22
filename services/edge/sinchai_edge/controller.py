"""SinchaiSlot Edge: the controller that sits beside the Altivar drive.

It is deterministic and works with no network:
  * holds the current plan (cached on disk) and runs each slot on the drive through DriveAdapter
  * only runs a water slot that is paid or unlocked; unlock codes are verified offline
  * meters water from drive telemetry (drive-as-meter) and stops the booking at its m3
  * enforces the local copy of the groundwater budget and the dry-run cut-off
  * buffers telemetry and events while the uplink is down and flushes them when it returns

Messages follow docs/edge-protocol.md (MQTT topics sinchai/<pump>/...).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from sinchai_devices.adapter import DriveAdapter, DriveTelemetry
from sinchai_devices.meter import DriveMeter
from sinchai_jal.budget import DryRunGuard


# ---------------------------------------------------------------------------
# Offline unlock codes
# ---------------------------------------------------------------------------

def unlock_code(secret: bytes, pump_id: str, booking_id: str, m3: float, counter: int) -> str:
    """9-digit code, read out by IVR or sent by SMS, typed on the starter keypad or spoken to the Saur Mitra.

    HMAC-SHA256 over pump, booking, volume (0.1 m3 units) and a monotonic counter; the edge keeps
    the last counter it accepted, so a code can be used once and old codes cannot be replayed.
    """
    msg = f"{pump_id}|{booking_id}|{int(round(m3 * 10))}|{counter}".encode()
    d = hmac.new(secret, msg, hashlib.sha256).digest()
    return f"{int.from_bytes(d[:8], 'big') % 10**9:09d}"


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

@dataclass
class EdgeSlot:
    start: str  # ISO local time
    end: str
    kind: str  # water | mill | chaff | battery | idle
    booking_id: str | None = None
    m3: float = 0.0
    paid: bool = False
    counter: int | None = None  # unlock counter if paid offline


@dataclass
class EdgePlan:
    pump_id: str
    version: int
    slots: list[EdgeSlot]
    budget_remaining_m3: float

    @classmethod
    def from_json(cls, d: dict) -> EdgePlan:
        return cls(d["pump_id"], d["version"], [EdgeSlot(**s) for s in d["slots"]], d["budget_remaining_m3"])

    def to_json(self) -> dict:
        return {"pump_id": self.pump_id, "version": self.version, "slots": [asdict(s) for s in self.slots],
                "budget_remaining_m3": self.budget_remaining_m3}


class Uplink(Protocol):
    connected: bool

    def publish(self, topic: str, payload: dict) -> bool: ...


@dataclass
class MemoryUplink:
    """In-process uplink for tests and the offline demo."""

    connected: bool = True
    sent: list[tuple[str, dict]] = field(default_factory=list)

    def publish(self, topic: str, payload: dict) -> bool:
        if not self.connected:
            return False
        self.sent.append((topic, payload))
        return True


class MqttUplink:
    """paho-mqtt uplink. Broker URL like mqtt://localhost:1883."""

    def __init__(self, host: str = "localhost", port: int = 1883, client_id: str = "sinchai-edge"):
        import paho.mqtt.client as mqtt

        self.connected = False
        self.c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self.c.on_connect = lambda *a, **k: setattr(self, "connected", True)
        self.c.on_disconnect = lambda *a, **k: setattr(self, "connected", False)
        self.c.connect_async(host, port, keepalive=30)
        self.c.loop_start()

    def publish(self, topic: str, payload: dict) -> bool:
        if not self.connected:
            return False
        r = self.c.publish(topic, json.dumps(payload), qos=1)
        return r.rc == 0

    def subscribe(self, topic: str, handler) -> None:
        self.c.subscribe(topic, qos=1)
        self.c.message_callback_add(topic, lambda c, u, m: handler(json.loads(m.payload)))


@dataclass
class EdgeController:
    pump_id: str
    drive: DriveAdapter
    secret: bytes
    uplink: Uplink
    state_dir: Path | None = None
    meter: DriveMeter = field(default_factory=DriveMeter)
    dry_guard: DryRunGuard = field(default_factory=DryRunGuard)
    plan: EdgePlan | None = None
    last_counter: int = -1
    outbox: deque = field(default_factory=lambda: deque(maxlen=50_000))
    active: EdgeSlot | None = None
    delivered_m3: dict[str, float] = field(default_factory=dict)
    kwh_by_booking: dict[str, float] = field(default_factory=dict)
    _underload_s: float = 0.0
    _last_ts: datetime | None = None
    tripped: str | None = None
    budget_used_m3: float = 0.0
    events: list[dict] = field(default_factory=list)

    # ---------------- plan and codes ----------------
    def load_cached_plan(self) -> None:
        if self.state_dir and (self.state_dir / "plan.json").exists():
            self.plan = EdgePlan.from_json(json.loads((self.state_dir / "plan.json").read_text()))
            st = json.loads((self.state_dir / "state.json").read_text()) if (self.state_dir / "state.json").exists() else {}
            self.last_counter = st.get("last_counter", -1)
            self.budget_used_m3 = st.get("budget_used_m3", 0.0)
            self.delivered_m3 = st.get("delivered_m3", {})

    def _persist(self) -> None:
        if not self.state_dir:
            return
        self.state_dir.mkdir(parents=True, exist_ok=True)
        if self.plan:
            (self.state_dir / "plan.json").write_text(json.dumps(self.plan.to_json()))
        (self.state_dir / "state.json").write_text(json.dumps(
            {"last_counter": self.last_counter, "budget_used_m3": self.budget_used_m3, "delivered_m3": self.delivered_m3}))

    def receive_plan(self, d: dict) -> None:
        p = EdgePlan.from_json(d)
        if self.plan and p.version <= self.plan.version:
            return
        # Keep payment flags already granted on this device.
        if self.plan:
            paid = {s.booking_id: (s.paid, s.counter) for s in self.plan.slots if s.booking_id}
            for s in p.slots:
                if s.booking_id in paid and paid[s.booking_id][0]:
                    s.paid, s.counter = paid[s.booking_id]
        self.plan = p
        self.budget_used_m3 = 0.0
        self._persist()
        self._emit("event", {"type": "plan_accepted", "version": p.version})

    def enter_code(self, booking_id: str, code: str) -> bool:
        if not self.plan:
            return False
        for s in self.plan.slots:
            if s.booking_id != booking_id:
                continue
            for counter in range(self.last_counter + 1, self.last_counter + 50):
                if hmac.compare_digest(unlock_code(self.secret, self.pump_id, booking_id, s.m3, counter), code):
                    for t in self.plan.slots:
                        if t.booking_id == booking_id:
                            t.paid, t.counter = True, counter
                    self.last_counter = counter
                    self._persist()
                    self._emit("event", {"type": "unlocked", "booking_id": booking_id, "counter": counter})
                    return True
        self._emit("event", {"type": "unlock_rejected", "booking_id": booking_id})
        return False

    # ---------------- uplink ----------------
    def _emit(self, kind: str, payload: dict) -> None:
        msg = {"pump_id": self.pump_id, **payload}
        self.events.append({"kind": kind, **msg})
        self.outbox.append((f"sinchai/{self.pump_id}/{kind}", msg))
        self.flush()

    def flush(self) -> int:
        n = 0
        while self.outbox and self.uplink.connected:
            topic, msg = self.outbox[0]
            if not self.uplink.publish(topic, msg):
                break
            self.outbox.popleft()
            n += 1
        return n

    # ---------------- control loop ----------------
    def _slot_at(self, now: datetime) -> EdgeSlot | None:
        if not self.plan:
            return None
        iso = now.isoformat(timespec="minutes")
        for s in self.plan.slots:
            if s.start <= iso < s.end:
                return s
        return None

    def _budget_left(self) -> float:
        return (self.plan.budget_remaining_m3 - self.budget_used_m3) if self.plan else 0.0

    def step(self, now: datetime) -> DriveTelemetry:
        t = self.drive.read_telemetry()
        dt_h = 0.0 if self._last_ts is None else max((now - self._last_ts).total_seconds(), 0) / 3600
        self._last_ts = now

        # Meter what just happened.
        if self.active and self.active.kind == "water" and t.state == "operation_enabled":
            est = self.meter.estimate(t)
            bid = self.active.booking_id or "-"
            m3 = est.flow_m3h * dt_h
            self.delivered_m3[bid] = self.delivered_m3.get(bid, 0.0) + m3
            self.kwh_by_booking[bid] = self.kwh_by_booking.get(bid, 0.0) + t.power_kw * dt_h
            self.budget_used_m3 += m3
            expected = float(self.meter.pump.power_at_speed(t.freq_hz / 50)) if t.freq_hz > 0 else 0.0
            if self.dry_guard.underloaded(expected, t.power_kw):
                self._underload_s += dt_h * 3600
            else:
                self._underload_s = 0.0
            if self._underload_s >= self.dry_guard.persist_s:
                self.tripped = "dry_run"
                self.drive.stop()
                self._emit("event", {"type": "dry_run_cutoff", "booking_id": bid, "ts": now.isoformat()})

        if t.fault and self.tripped != t.fault:
            self.tripped = t.fault
            self._emit("event", {"type": "drive_fault", "fault": t.fault, "lft": t.fault_lft, "ts": now.isoformat()})

        slot = self._slot_at(now)
        want_run = False
        if slot and slot.kind == "water" and slot.paid and not self.tripped and t.fault is None:
            done = self.delivered_m3.get(slot.booking_id or "-", 0.0) >= slot.m3 - 1e-6
            if self._budget_left() <= 0:
                if self.active is slot:
                    self._emit("event", {"type": "budget_cutoff", "booking_id": slot.booking_id, "ts": now.isoformat()})
            elif not done:
                want_run = True

        if self.active and (self.active is not slot or not want_run):
            self._close_slot(now)
        if want_run and self.active is None:
            self.active = slot
            self.drive.start(50.0)
            self._emit("event", {"type": "slot_started", "booking_id": slot.booking_id, "ts": now.isoformat()})
        elif not want_run and t.state == "operation_enabled" and self.active is None:
            self.drive.stop()

        self._emit("telemetry", {"ts": now.isoformat(), **t.model_dump(exclude={"ts"}),
                                 "active_booking": self.active.booking_id if self.active else None,
                                 "budget_left_m3": round(self._budget_left(), 2)})
        self._persist()
        return t

    def _close_slot(self, now: datetime) -> None:
        s = self.active
        self.active = None
        self.drive.stop()
        if s and s.kind == "water":
            bid = s.booking_id or "-"
            self._emit("event", {
                "type": "slot_completed", "booking_id": bid, "ts": now.isoformat(),
                "m3": round(self.delivered_m3.get(bid, 0.0), 3), "kwh": round(self.kwh_by_booking.get(bid, 0.0), 4),
                "method": "drive-estimate", "meter_k": round(self.meter.k, 4),
            })

    def status(self) -> dict[str, Any]:
        return {"pump_id": self.pump_id, "plan_version": self.plan.version if self.plan else None,
                "active": self.active.booking_id if self.active else None, "tripped": self.tripped,
                "budget_left_m3": round(self._budget_left(), 2), "outbox": len(self.outbox),
                "uplink": self.uplink.connected}
