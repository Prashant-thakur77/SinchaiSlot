"""Live village state for the platform and the demo.

One pump cluster (P1) on the real held-out demo day from reports/proof.json. The day is planned in
30-minute slots by Surya Planner on the P10/P50/P90 forecast. A simulated clock drives the edge
controller, which runs the in-process Altivar drive model on the day's real sun. At 13:40 the
nowcast replaces the afternoon forecast with what the sky is actually doing; the planner re-flows,
explains the change, and Saathi calls the farmers whose slots moved.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import numpy as np
from sinchai_devices.adapter import InProcessAltivar
from sinchai_devices.altivar_model import AltivarModel
from sinchai_devices.physics import default_pump
from sinchai_edge.controller import EdgeController, EdgePlan, EdgeSlot, MemoryUplink
from sinchai_jal.budget import WaterBudget
from sinchai_planner.optimizer import Loads, Plan, PlanInput, Request, Scenario, solve
from sinchai_planner.replan import explain_diff, ranges
from sinchai_schemas import constants as C

from . import db
from .settings import ROOT, settings

SLOT_MIN = 30
DAY_START_H = 6
N_SLOTS = 24  # 06:00 - 18:00
CLOUD_AT = "13:40"


def load_proof() -> dict:
    for name in ("proof.json", "proof_quick.json"):
        p = ROOT / "reports" / name
        if p.exists():
            return json.loads(p.read_text())
    raise FileNotFoundError("reports/proof.json missing: run `make proof`")


def half_hour_series(hourly: list[float]) -> np.ndarray:
    """Hourly means labelled at HH:30 -> 30-minute slots 06:00-18:00 by interpolation at slot centres."""
    hours = np.array([6.5 + i + 0.5 for i in range(len(hourly))])  # centre of each labelled hour
    centres = np.array([DAY_START_H + (k + 0.5) * SLOT_MIN / 60 for k in range(N_SLOTS)])
    return np.clip(np.interp(centres, hours, hourly, left=0.0, right=0.0), 0, None)


@dataclass
class Event:
    ts: str
    kind: str
    data: dict


class EventBus:
    def __init__(self) -> None:
        self.log: deque[Event] = deque(maxlen=2000)
        self.subscribers: list[asyncio.Queue] = []
        self.lock = threading.Lock()

    def publish(self, ts: str, kind: str, data: dict) -> None:
        ev = Event(ts, kind, data)
        with self.lock:
            self.log.append(ev)
            subs = list(self.subscribers)
        for q in subs:
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(ev)


@dataclass
class VillageState:
    day: str
    pv_actual: np.ndarray
    q10: np.ndarray
    q50: np.ndarray
    q90: np.ndarray
    clock: datetime
    pump_id: str = "P1"
    plan: Plan | None = None
    plan_input: PlanInput | None = None
    scenarios: list[Scenario] = field(default_factory=list)
    plan_version: int = 0
    diffs: list[dict] = field(default_factory=list)
    cloud_applied: bool = False
    bus: EventBus = field(default_factory=EventBus)
    budget: WaterBudget = field(default_factory=lambda: WaterBudget.for_cluster())
    model: AltivarModel | None = None
    edge: EdgeController | None = None
    uplink: MemoryUplink = field(default_factory=MemoryUplink)
    callbacks: list[dict] = field(default_factory=list)
    lock: threading.RLock = field(default_factory=threading.RLock)
    mill_backlog_kg: float = 120.0
    chaff_hours: float = 2.0
    battery_kwh: float = 6.0
    offers: dict = field(default_factory=dict)
    _display_scen: list = field(default_factory=list)

    # ---------------- time ----------------
    def slot_index(self, t: datetime | None = None) -> int:
        t = t or self.clock
        return int(((t.hour - DAY_START_H) * 60 + t.minute) // SLOT_MIN)

    def slot_label(self, k: int) -> str:
        m = DAY_START_H * 60 + k * SLOT_MIN
        return f"{m // 60:02d}:{m % 60:02d}"

    def pv_now(self, t: datetime | None = None) -> float:
        t = t or self.clock
        x = (t.hour + t.minute / 60 + t.second / 3600 - DAY_START_H) * 60 / SLOT_MIN - 0.5
        return float(np.interp(x, np.arange(N_SLOTS), self.pv_actual, left=0.0, right=0.0))

    # ---------------- planning ----------------
    def _requests(self, s: db.Session) -> list[Request]:
        out = []
        for b in s.query(db.Booking).filter(db.Booking.day == self.day, db.Booking.pump_id == self.pump_id,
                                            db.Booking.status.in_(["confirmed", "paid", "running"])).all():
            f = s.get(db.Farmer, b.farmer_id)
            left = max(b.m3_requested - b.m3_delivered, 0.0)
            if left <= 0.05:
                continue
            p = s.get(db.Plot, b.plot_id)
            prio = 1.0 + (0.5 if p and p.stage == "mid" else 0.0) + (0.5 if b.paid else 0.0)
            out.append(Request(b.id, b.farmer_id, left, prio, due_today=True, tenant=bool(f and f.tenant)))
        return out

    def scenarios_now(self) -> list[Scenario]:
        q10, q50, q90 = self.q10.copy(), self.q50.copy(), self.q90.copy()
        if self.cloud_applied:
            # Nowcast after 13:40: the afternoon follows the observed sky; band narrows around it.
            k0 = self.slot_index()
            obs = self.pv_actual
            q50[k0:] = obs[k0:]
            q10[k0:] = obs[k0:] * 0.85
            q90[k0:] = np.minimum(obs[k0:] * 1.12, self.q90[k0:])
        return [Scenario("P10", 0.3, q10), Scenario("P50", 0.4, q50), Scenario("P90", 0.3, q90)]

    def build_input(self, s, freeze_from_now: bool = False, extra: list[Request] | None = None) -> PlanInput:
        """Plan input from the bookings and the current forecast. Past slots get zero sun in the copy the
        solver sees; the display and the plan-diff explainer keep the real forecast (self.scenarios)."""
        reqs = self._requests(s) + list(extra or [])
        scen = self.scenarios_now()
        solver_scen = [Scenario(x.name, x.prob, x.pv_kw.copy()) for x in scen]
        frozen: dict[int, str] = {}
        now_k = self.slot_index()
        if freeze_from_now and self.plan is not None:
            for t in range(min(now_k, N_SLOTS)):
                frozen[t] = "idle"
                for sc in solver_scen:
                    sc.pv_kw[t] = 0.0
            # Freeze the running slot and the next one (60 min) so nobody is moved at the last moment.
            ids = {r.id for r in reqs}
            for t in range(now_k, min(now_k + 60 // SLOT_MIN, N_SLOTS)):
                a = self.plan.slots[t].action
                if a.startswith("req:") and a[4:] not in ids:
                    a = "idle"
                frozen[t] = a
        op = [k for k in range(N_SLOTS) if 7 * 60 <= DAY_START_H * 60 + k * SLOT_MIN < 17 * 60]
        self._display_scen = scen
        return PlanInput(
            slot_starts=[f"{self.day}T{self.slot_label(k)}" for k in range(N_SLOTS)], slot_h=SLOT_MIN / 60,
            scenarios=solver_scen, requests=reqs,
            loads=Loads(mill_backlog_kg=self.mill_backlog_kg, mill_kwh_per_kg=C.get("mill_kwh_per_kg"),
                        mill_max_kw=C.get("mill_rated_kw"),
                        mill_value_rs_per_kwh=C.get("mill_rs_per_kg") / C.get("mill_kwh_per_kg"),
                        chaff_hours=self.chaff_hours, chaff_kw=C.get("chaff_cutter_kw"),
                        chaff_value_rs_per_kwh=C.get("chaff_cutter_rs_per_hour") / C.get("chaff_cutter_kw"),
                        battery_kwh_demand=self.battery_kwh,
                        battery_value_rs_per_kwh=C.get("battery_pack_rs_per_charge") / C.get("battery_pack_kwh")),
            budget_remaining_m3=self.budget.remaining(datetime.fromisoformat(self.day).date()),
            operator_slots=op, frozen=frozen or None, time_limit_s=8.0,
        )

    def solve_plan(self, reason: str = "initial", freeze_from_now: bool = False) -> dict:
        with self.lock, db.session() as s:
            inp = self.build_input(s, freeze_from_now)
        plan = solve(inp)
        return self.adopt(plan, inp, reason, self._display_scen)

    def adopt(self, plan: Plan, inp: PlanInput, reason: str, display_scen: list[Scenario]) -> dict:
        """Make `plan` the current plan: keep past slots as they ran, write slot times to bookings,
        explain the change, push it to the edge and publish it."""
        with self.lock, db.session() as s:
            now_k = self.slot_index()
            old_plan, old_scen = self.plan, self.scenarios
            if old_plan is not None:
                for t in range(min(now_k, N_SLOTS)):
                    plan.slots[t].action = old_plan.slots[t].action
                    plan.slots[t].household = old_plan.slots[t].household
            self.plan, self.plan_input, self.scenarios = plan, inp, display_scen
            self.plan_version += 1
            booking_slots: dict[str, list[int]] = {}
            for sp in plan.slots:
                if sp.action.startswith("req:"):
                    booking_slots.setdefault(sp.action[4:], []).append(sp.slot)
            for b in s.query(db.Booking).filter(db.Booking.day == self.day, db.Booking.pump_id == self.pump_id).all():
                ks = booking_slots.get(b.id)
                if ks:
                    b.slot_start = self.slot_label(min(ks))
                    b.slot_end = self.slot_label(max(ks) + 1)
                elif b.status in ("confirmed", "paid") and b.m3_delivered < b.m3_requested - 0.05:
                    b.slot_start = b.slot_end = None
            s.commit()
            changes = []
            if old_plan is not None:
                changes = [c.__dict__ for c in explain_diff(old_plan, plan, old_scen, display_scen)]
                # Slots that already ran cannot have moved; drop artefacts from the frozen past.
                cutoff = self.slot_label(now_k)

                def future_m3(pl: Plan, action: str) -> float:
                    return sum(sp.water_m3.get("P50", 0.0) for sp in pl.slots
                               if sp.action == action and self.slot_label(sp.slot) >= cutoff)

                kept = []
                for c in changes:
                    c["old_slots"] = [x for x in c["old_slots"] if x >= cutoff]
                    c["new_slots"] = [x for x in c["new_slots"] if x >= cutoff]
                    if c["old_slots"] == c["new_slots"]:
                        continue
                    if c["kind"] in ("moved", "added", "dropped"):
                        a = f"req:{c['subject']}"
                        c["old_m3"] = round(future_m3(old_plan, a), 1)
                        c["new_m3"] = round(future_m3(plan, a), 1)
                        if not c["old_slots"] and c["new_slots"]:
                            c["kind"] = "added"
                        elif c["old_slots"] and not c["new_slots"]:
                            c["kind"] = "dropped"
                    cause_en, cause_hi = c["reason_en"].split(": ")[0], c["reason_hi"].split(": ")[0]
                    if c["kind"] == "load_moved" and c["subject"] == "battery":
                        pass
                    elif c["kind"] == "added":
                        c["reason_en"] = f"{cause_en}: water added {ranges(c['new_slots'])}"
                        c["reason_hi"] = f"{cause_hi}: {ranges(c['new_slots'])} बजे पानी का समय जोड़ा गया"
                    elif c["kind"] == "dropped":
                        c["reason_en"] = f"{cause_en}: {ranges(c['old_slots'])} released, carried to the next sunny window"
                        c["reason_hi"] = f"{cause_hi}: {ranges(c['old_slots'])} का समय अगली धूप वाली खिड़की में"
                    else:
                        c["reason_en"] = f"{cause_en}: {c['subject']} {ranges(c['old_slots'])} -> {ranges(c['new_slots'])}"
                        c["reason_hi"] = f"{cause_hi}: {ranges(c['old_slots'])} से {ranges(c['new_slots'])}"
                    kept.append(c)
                changes = kept
                self.diffs.append({"version": self.plan_version, "at": self.clock.strftime("%H:%M"), "reason": reason,
                                   "changes": changes})
            self._push_edge_plan()
            summary = self.plan_summary()
            self.bus.publish(self.clock.isoformat(), "plan", {"version": self.plan_version, "reason": reason,
                                                              "changes": changes, "summary": summary})
            return {"version": self.plan_version, "status": plan.status, "solve_s": round(plan.solve_s, 3),
                    "mip_gap": plan.mip_gap, "changes": changes, "summary": summary}

    def plan_summary(self) -> dict:
        p = self.plan
        if p is None:
            return {}
        return {
            "water_m3_p50": round(p.total("water", "P50"), 1), "water_m3_p10": round(p.total("water", "P10"), 1),
            "mill_kwh_p50": round(p.total("mill", "P50"), 2), "chaff_kwh_p50": round(p.total("chaff", "P50"), 2),
            "battery_kwh_p50": round(p.total("battery", "P50"), 2),
            "pv_kwh_p50": round(float(np.sum(self.scenarios[1].pv_kw)) * SLOT_MIN / 60, 2),
        }

    def _push_edge_plan(self) -> None:
        if self.edge is None or self.plan is None:
            return
        with db.session() as s:
            paid = {b.id: b.paid for b in s.query(db.Booking).filter(db.Booking.day == self.day).all()}
            m3 = {b.id: b.m3_requested for b in s.query(db.Booking).filter(db.Booking.day == self.day).all()}
        slots = []
        for sp in self.plan.slots:
            start = f"{self.day}T{self.slot_label(sp.slot)}"
            end = f"{self.day}T{self.slot_label(sp.slot + 1)}"
            if sp.action.startswith("req:"):
                bid = sp.action[4:]
                slots.append(EdgeSlot(start, end, "water", bid, m3.get(bid, 0.0), paid.get(bid, False)))
            else:
                slots.append(EdgeSlot(start, end, sp.action if sp.action != "idle" else "idle"))
        ep = EdgePlan(self.pump_id, self.plan_version, slots,
                      self.budget.remaining(datetime.fromisoformat(self.day).date())).to_json()
        self.edge.receive_plan(ep)

    # ---------------- simulation ----------------
    def advance(self, minutes: float, step_s: float = 20.0) -> None:
        """Advance the simulated clock, stepping the edge controller and drive."""
        end = self.clock + timedelta(minutes=minutes)
        while self.clock < end:
            self.clock = min(self.clock + timedelta(seconds=step_s), end)
            self._step()

    def _step(self) -> None:
        if self.edge is None:
            return
        with self.lock:
            hhmm = self.clock.strftime("%H:%M")
            if not self.cloud_applied and hhmm >= CLOUD_AT:
                self.cloud_applied = True
                self.bus.publish(self.clock.isoformat(), "nowcast", {
                    "message": "Forecast band dropped: afternoon sun now tracking below P10",
                    "slots_affected": [self.slot_label(k) for k in range(self.slot_index(), N_SLOTS)
                                       if self.pv_actual[k] < 0.9 * self.q50[k] and self.q50[k] > 0.3]})
                res = self.solve_plan(reason=f"cloud band at {CLOUD_AT}", freeze_from_now=True)
                self._callbacks_for(res["changes"])
            n_before = len(self.edge.events)
            self.edge.step(self.clock)
            for ev in self.edge.events[n_before:]:
                if ev["kind"] == "event":
                    self._on_edge_event(ev)
            t = self.edge.drive.read_telemetry()
            self.bus.publish(self.clock.isoformat(), "telemetry", {
                **t.model_dump(), "pv_kw": round(self.pv_now(), 3), **(self.model.ui_extras() if self.model else {}),
                "active_booking": self.edge.active.booking_id if self.edge.active else None})

    def _on_edge_event(self, ev: dict) -> None:
        from .ledger_service import record_water_receipt

        typ = ev.get("type")
        self.bus.publish(self.clock.isoformat(), "edge", ev)
        if typ == "slot_completed" and ev.get("m3", 0) > 0:
            with db.session() as s:
                b = s.get(db.Booking, ev["booking_id"])
                if b is None:
                    return
                delta = ev["m3"] - b.m3_delivered
                b.m3_delivered = ev["m3"]
                if b.m3_delivered >= b.m3_requested - 0.3:
                    b.status = "completed"
                s.commit()
                if delta > 0.01:
                    self.budget.record(datetime.fromisoformat(self.day).date(), delta)
                    r = record_water_receipt(s, b, delta, ev.get("kwh", 0.0), self.clock)
                    self.bus.publish(self.clock.isoformat(), "receipt", r)

    def _callbacks_for(self, changes: list[dict]) -> None:
        from .agents.saathi import callback_message

        with db.session() as s:
            for c in changes:
                if c["kind"] not in ("moved", "dropped", "added") or not c.get("household"):
                    continue
                f = s.get(db.Farmer, c["household"])
                if f is None:
                    continue
                msg = callback_message(f, c)
                cb = {"at": self.clock.strftime("%H:%M"), "farmer_id": f.id, "name": f.display_name,
                      "language": f.language, "channel": "ivr_callback", "text": msg, "change": c}
                self.callbacks.append(cb)
                self.bus.publish(self.clock.isoformat(), "callback", cb)

    def snapshot(self) -> dict[str, Any]:
        p = self.plan
        with db.session() as s:
            bookings = {b.id: b for b in s.query(db.Booking).filter(db.Booking.day == self.day).all()}
            farmers = {f.id: f for f in s.query(db.Farmer).all()}
        slots = []
        if p:
            for sp in p.slots:
                bid = sp.action[4:] if sp.action.startswith("req:") else None
                b = bookings.get(bid) if bid else None
                f = farmers.get(b.farmer_id) if b else None
                slots.append({"slot": sp.slot, "start": self.slot_label(sp.slot), "action": sp.action.split(":")[0],
                              "booking_id": bid, "farmer": f.display_name if f else None,
                              "tenant": f.tenant if f else None,
                              "water_m3": {k: round(v, 2) for k, v in sp.water_m3.items()},
                              "mill_kwh": round(sp.mill_kwh["P50"], 2), "chaff_kwh": round(sp.chaff_kwh["P50"], 2),
                              "battery_kwh": round(sp.battery_kwh["P50"], 2)})
        return {
            "day": self.day, "clock": self.clock.strftime("%H:%M"), "plan_version": self.plan_version,
            "cloud_applied": self.cloud_applied, "slots": slots,
            "forecast": {"labels": [self.slot_label(k) for k in range(N_SLOTS)],
                         "q10": self.q10.round(3).tolist(), "q50": self.q50.round(3).tolist(),
                         "q90": self.q90.round(3).tolist(), "actual": self.pv_actual.round(3).tolist(),
                         "nowcast": [round(float(s.pv_kw[k]), 3) for s in self.scenarios[1:2] for k in range(N_SLOTS)]
                         if self.scenarios else []},
            "summary": self.plan_summary(), "diffs": self.diffs[-5:], "callbacks": self.callbacks[-10:],
            "budget": {"annual_m3": round(self.budget.annual_m3, 0),
                       "remaining_m3": round(self.budget.remaining(datetime.fromisoformat(self.day).date()), 0),
                       "used_m3": {k: round(v, 1) for k, v in self.budget.used_m3.items()}},
            "edge": self.edge.status() if self.edge else None,
        }


_STATE: VillageState | None = None


def get_state() -> VillageState:
    global _STATE
    if _STATE is None:
        _STATE = build_state()
    return _STATE


def reset_state() -> VillageState:
    global _STATE
    from . import cluster

    cluster.reset()
    _STATE = build_state()
    return _STATE


def build_state(start_hhmm: str = "06:00") -> VillageState:
    proof = load_proof()
    d = proof["demo_day"]
    day = d["date"]
    st = VillageState(
        day=day,
        pv_actual=half_hour_series(d["pv_actual_kw"]), q10=half_hour_series(d["pv_q10_kw"]),
        q50=half_hour_series(d["pv_q50_kw"]), q90=half_hour_series(d["pv_q90_kw"]),
        clock=datetime.fromisoformat(f"{day}T{start_hhmm}"),
    )
    t0 = time.monotonic()
    st.model = AltivarModel(pump=default_pump(), pv_kw=lambda now: st.pv_now(),
                            clock=lambda: (st.clock - datetime.fromisoformat(f"{day}T00:00")).total_seconds())
    _ = t0
    st.edge = EdgeController(st.pump_id, InProcessAltivar(st.model), settings().edge_secret.encode(), st.uplink)
    # Budget used so far this season, from the ledger.
    with db.session() as s:
        used = sum(r.m3 for r in s.query(db.LedgerRow).filter(db.LedgerRow.kind == "water", db.LedgerRow.pump_id == st.pump_id,
                                                             db.LedgerRow.start < day).all()
                   if r.start[:4] == day[:4] and r.start[5:7] in ("01", "02", "03", "04", "05", "06")
                   and int(r.start[5:7]) >= 3)
        st.budget.used_m3["zaid"] = min(used, st.budget.season_cap("zaid"))
    st.solve_plan("initial")
    return st
