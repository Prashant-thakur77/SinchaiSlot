"""Multi-pump cluster: neighbouring pumps, booking transfer, data health and per-borewell water quality.

P1 is the live pump (edge controller + drive model, the demo story). P2 and P3 are its neighbours: each has
its own farmers, bookings and ledger history, and is planned by the same solver on the same day's forecast
(the cluster shares one sky). When a pump faults or fills up, bookings on plots within channel reach of a
neighbour can move there; the move needs the farmer's or Saur Mitra's confirmation like any booking change.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from datetime import datetime

from sinchai_edge.health import assess
from sinchai_jal.quality import card
from sinchai_planner.optimizer import Loads, Plan, PlanInput, Request, Scenario, solve
from sinchai_schemas import constants as C

from . import db
from .state import N_SLOTS, SLOT_MIN, VillageState, get_state

# Borewell EC from the starter's probe (SIMULATED readings for the demo cluster).
BOREWELL_EC_DSM = {"P1": 0.62, "P2": 0.94, "P3": 0.48}
# P3's edge stopped reporting on the demo morning (SIMULATED outage, to show the data-health monitor).
SILENT_SINCE = {"P3": "10:05"}


def distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    k = 111_320.0
    dx = (lon2 - lon1) * k * math.cos(math.radians((lat1 + lat2) / 2))
    dy = (lat2 - lat1) * k
    return math.hypot(dx, dy)


@dataclass
class Neighbour:
    pump_id: str
    plan: Plan | None = None
    version: int = 0
    lock: threading.RLock = field(default_factory=threading.RLock)

    def requests(self, s, day: str) -> list[Request]:
        out = []
        for b in s.query(db.Booking).filter(db.Booking.day == day, db.Booking.pump_id == self.pump_id,
                                            db.Booking.status.in_(["confirmed", "paid", "running"])).all():
            left = max(b.m3_requested - b.m3_delivered, 0.0)
            if left <= 0.05:
                continue
            f = s.get(db.Farmer, b.farmer_id)
            out.append(Request(b.id, b.farmer_id, left, 1.0 + (0.5 if b.paid else 0.0), due_today=True,
                               tenant=bool(f and f.tenant)))
        return out

    def plan_input(self, st: VillageState, s, extra: list[Request] | None = None) -> PlanInput:
        scen = st.scenarios_now()
        now_k = st.slot_index()
        solver = []
        for x in scen:
            pv = x.pv_kw.copy()
            pv[: max(0, min(now_k, N_SLOTS))] = 0.0  # the past cannot be planned
            solver.append(Scenario(x.name, x.prob, pv))
        op = [k for k in range(N_SLOTS) if 7 * 60 <= 6 * 60 + k * SLOT_MIN < 17 * 60]
        return PlanInput(
            slot_starts=[f"{st.day}T{st.slot_label(k)}" for k in range(N_SLOTS)], slot_h=SLOT_MIN / 60,
            scenarios=solver, requests=self.requests(s, st.day) + list(extra or []),
            loads=Loads(),  # neighbours run water only; the mill and battery packs sit at P1
            budget_remaining_m3=st.budget.remaining(datetime.fromisoformat(st.day).date()),
            operator_slots=op, time_limit_s=6.0,
        )

    def solve(self, st: VillageState) -> Plan:
        with self.lock, db.session() as s:
            inp = self.plan_input(st, s)
        plan = solve(inp)
        with self.lock, db.session() as s:
            self.plan, self.version = plan, self.version + 1
            slots: dict[str, list[int]] = {}
            for sp in plan.slots:
                if sp.action.startswith("req:"):
                    slots.setdefault(sp.action[4:], []).append(sp.slot)
            for b in s.query(db.Booking).filter(db.Booking.day == st.day, db.Booking.pump_id == self.pump_id).all():
                ks = slots.get(b.id)
                b.slot_start = st.slot_label(min(ks)) if ks else None
                b.slot_end = st.slot_label(max(ks) + 1) if ks else None
            s.commit()
        self._publish(st)
        return plan

    def _publish(self, st: VillageState) -> None:
        """Send this pump's own plan to its external edge controller (docker compose runs P2's edge)."""
        from . import bridge

        if self.plan is None:
            return
        with db.session() as s:
            bs = {b.id: b for b in s.query(db.Booking).filter(db.Booking.day == st.day,
                                                             db.Booking.pump_id == self.pump_id).all()}
        slots = []
        for sp in self.plan.slots:
            start, end = f"{st.day}T{st.slot_label(sp.slot)}", f"{st.day}T{st.slot_label(sp.slot + 1)}"
            if sp.action.startswith("req:") and sp.action[4:] in bs:
                b = bs[sp.action[4:]]
                slots.append({"start": start, "end": end, "kind": "water", "booking_id": b.id,
                              "m3": b.m3_requested, "paid": b.paid})
            else:
                slots.append({"start": start, "end": end, "kind": "idle"})
        bridge.publish_plan(self.pump_id, {"pump_id": self.pump_id, "version": self.version, "slots": slots,
                                           "budget_remaining_m3": st.budget.remaining(
                                               datetime.fromisoformat(st.day).date())})


_N: dict[str, Neighbour] = {}
_N_DAY: str | None = None


def neighbours() -> dict[str, Neighbour]:
    global _N_DAY
    st = get_state()
    if st.day != _N_DAY or not _N:
        _N.clear()
        with db.session() as s:
            for p in s.query(db.Pump).filter(db.Pump.id != st.pump_id).order_by(db.Pump.id).all():
                _N[p.id] = Neighbour(p.id)
        _N_DAY = st.day
    for n in _N.values():
        if n.plan is None:
            n.solve(st)
    return _N


def reset() -> None:
    global _N_DAY
    _N.clear()
    _N_DAY = None


def _plan_of(pump_id: str) -> Plan | None:
    st = get_state()
    return st.plan if pump_id == st.pump_id else neighbours()[pump_id].plan


def _served(plan: Plan | None, bid: str) -> float:
    if plan is None:
        return 0.0
    return round(plan.served_m3.get(bid, {}).get("P50", 0.0), 1)


# ---------------------------------------------------------------- health

def health(pump_id: str) -> dict:
    st = get_state()
    now = st.clock
    daylight = 6 <= now.hour < 18
    if pump_id == st.pump_id:
        t = st.edge.drive.read_telemetry() if st.edge else None
        running = bool(st.edge and st.edge.active)
        h = assess(pump_id, now, now, daylight=daylight, scheduled_water=running,
                   power_kw=t.power_kw if t else None, sun_kw=st.pv_now())
        return {**h.to_dict(), "source": "in-process edge (simulated drive)"}
    with db.session() as s:
        last = s.query(db.Telemetry).filter(db.Telemetry.pump_id == pump_id).order_by(db.Telemetry.ts.desc()).first()
    if last is not None:
        h = assess(pump_id, last.ts, datetime.utcnow(), daylight=True)
        return {**h.to_dict(), "source": "MQTT edge telemetry"}
    since = SILENT_SINCE.get(pump_id)
    seen = datetime.fromisoformat(f"{st.day}T{since}") if since and st.clock.strftime("%H:%M") > since else now
    h = assess(pump_id, seen, now, daylight=daylight)
    gone = since and h.status != "live"
    return {**h.to_dict(), "source": "SIMULATED edge" + (f" · outage scripted from {since}" if gone else "")}


# ---------------------------------------------------------------- views

def overview() -> dict:
    st = get_state()
    nb = neighbours()
    out = []
    with db.session() as s:
        pumps = s.query(db.Pump).order_by(db.Pump.id).all()
        for p in pumps:
            plan = st.plan if p.id == st.pump_id else nb[p.id].plan
            bs = s.query(db.Booking).filter(db.Booking.day == st.day, db.Booking.pump_id == p.id,
                                            db.Booking.status != "cancelled").all()
            open_bs = [b for b in bs if b.status in ("confirmed", "paid", "running")]
            short = [{"booking_id": b.id, "need_m3": round(b.m3_requested - b.m3_delivered, 1),
                      "expected_today_m3": _served(plan, b.id)} for b in open_bs
                     if _served(plan, b.id) < b.m3_requested - b.m3_delivered - 1.0]
            n_plots = s.query(db.Plot).filter(db.Plot.pump_id == p.id).count()
            fault = st.edge.drive.read_telemetry().fault if p.id == st.pump_id and st.edge else None
            out.append({
                "pump_id": p.id, "name": p.name, "kwp": p.kwp, "lon": p.lon, "lat": p.lat, "operator": p.operator,
                "plots": n_plots, "bookings_today": len(bs),
                "water_m3_p50": round(plan.total("water", "P50"), 1) if plan else 0.0,
                "requested_m3": round(sum(b.m3_requested for b in bs), 1), "short_today": short,
                "fault": fault if fault and fault != "NOF" else None, "live": p.id == st.pump_id,
                "health": health(p.id), "water_quality": card(p.id, BOREWELL_EC_DSM.get(p.id, 0.6)).to_dict(),
            })
    return {"day": st.day, "clock": st.clock.strftime("%H:%M"), "pumps": out,
            "transmitting": sum(1 for x in out if x["health"]["status"] in ("live", "late")),
            "context": {"value": C.get("ceew_pumps_transmitting_share"), "note": C.entry("ceew_pumps_transmitting_share").note}}


def transfer_options(booking_id: str) -> dict:
    """Neighbouring pumps that can reach this booking's plot, and what each would deliver today."""
    st = get_state()
    nb = neighbours()
    reach = C.get("transfer_max_channel_m")
    with db.session() as s:
        b = s.get(db.Booking, booking_id)
        if b is None:
            raise ValueError("unknown booking")
        plot = s.get(db.Plot, b.plot_id)
        f = s.get(db.Farmer, b.farmer_id)
        left = max(b.m3_requested - b.m3_delivered, 0.0)
        src = b.pump_id
        pumps = s.query(db.Pump).filter(db.Pump.id != src).order_by(db.Pump.id).all()
        here = _served(_plan_of(src), booking_id)
        opts = []
        for p in pumps:
            d = distance_m(plot.lon, plot.lat, p.lon, p.lat)
            o = {"pump_id": p.id, "name": p.name, "distance_m": round(d), "reachable": d <= reach}
            if d <= reach:
                hh = health(p.id)
                fault = p.id == st.pump_id and st.edge and st.edge.drive.read_telemetry().fault not in (None, "NOF")
                if hh["status"] in ("silent", "never") or fault:
                    o.update(reachable=False, reason="pump is not reporting" if not fault else "pump has a fault")
                else:
                    extra = [Request("MOVE", b.farmer_id, left, 1.5, True, tenant=bool(f and f.tenant))]
                    if p.id == st.pump_id:
                        inp = st.build_input(s, freeze_from_now=st.slot_index() > 0, extra=extra)
                    else:
                        inp = nb[p.id].plan_input(st, s, extra=extra)
                    plan = solve(inp)
                    o["expected_today_m3"] = round(plan.served_m3.get("MOVE", {}).get("P50", 0.0), 1)
                    ks = [sp.slot for sp in plan.slots if sp.action == "req:MOVE"]
                    o["slots"] = f"{st.slot_label(min(ks))}-{st.slot_label(max(ks) + 1)}" if ks else None
            opts.append(o)
    opts.sort(key=lambda o: (not o["reachable"], -o.get("expected_today_m3", 0), o["distance_m"]))
    return {"booking_id": booking_id, "from_pump": src, "need_m3": round(left, 1), "expected_here_m3": here,
            "max_channel_m": reach, "options": opts}


def transfer(booking_id: str, to_pump: str) -> dict:
    st = get_state()
    opts = transfer_options(booking_id)
    o = next((x for x in opts["options"] if x["pump_id"] == to_pump), None)
    if o is None or not o["reachable"]:
        raise ValueError(f"{to_pump} cannot reach this plot" + (f": {o.get('reason')}" if o and o.get("reason") else ""))
    src = opts["from_pump"]
    from sinchai_edge.controller import unlock_code

    from .settings import settings

    code = None
    with db.session() as s:
        b = s.get(db.Booking, booking_id)
        b.pump_id = to_pump
        b.slot_start = b.slot_end = None
        if b.paid:
            # Unlock codes are bound to the pump: the old pump's code will not open the new one.
            counter = st.edge.last_counter + 1 if to_pump == st.pump_id and st.edge else 0
            b.unlock_counter = counter
            code = unlock_code(settings().edge_secret.encode(), to_pump, b.id, b.m3_requested, counter)
        s.commit()
    if code and to_pump == st.pump_id and st.edge:
        st.edge.enter_code(booking_id, code)
    nb = neighbours()
    if to_pump == st.pump_id:
        st.solve_plan(reason=f"{booking_id} moved here from {src}", freeze_from_now=st.slot_index() > 0)
    else:
        nb[to_pump].solve(st)
    if src == st.pump_id:
        st.solve_plan(reason=f"{booking_id} moved to {to_pump}", freeze_from_now=st.slot_index() > 0)
    elif src in nb:
        nb[src].solve(st)
    with db.session() as s:
        b = s.get(db.Booking, booking_id)
        res = {"moved": True, "booking_id": booking_id, "from_pump": src, "to_pump": to_pump,
               "slot_start": b.slot_start, "slot_end": b.slot_end,
               "expected_today_m3": _served(_plan_of(to_pump), booking_id), "unlock_code": code,
               "note": "new unlock code for the new pump" if code else "pay to get the unlock code"}
    st.bus.publish(st.clock.isoformat(), "transfer", res)
    return res


def suggest_transfers(pump_id: str | None = None) -> dict:
    """When a pump is down (fault) or cannot fit a booking today, propose the best reachable neighbour for each."""
    st = get_state()
    pid = pump_id or st.pump_id
    plan = _plan_of(pid)
    fault = None
    if pid == st.pump_id and st.edge:
        f = st.edge.drive.read_telemetry().fault
        fault = f if f and f != "NOF" else None
    out = []
    with db.session() as s:
        bs = s.query(db.Booking).filter(db.Booking.day == st.day, db.Booking.pump_id == pid,
                                        db.Booking.status.in_(["confirmed", "paid"])).all()
        left = {b.id: b.m3_requested - b.m3_delivered for b in bs}
        cands = [bid for bid, v in left.items() if v > 0.3 and (fault or _served(plan, bid) < v - 1.0)]
    for bid in cands[:8]:
        o = transfer_options(bid)
        here = 0.0 if fault else o["expected_here_m3"]
        best = next((x for x in o["options"] if x["reachable"] and x.get("expected_today_m3", 0) > here + 1.0), None)
        if best:
            out.append({"booking_id": bid, "need_m3": o["need_m3"], "expected_here_m3": here, "to_pump": best["pump_id"],
                        "distance_m": best["distance_m"], "expected_today_m3": best["expected_today_m3"],
                        "slots": best.get("slots")})
    return {"pump_id": pid, "fault": fault, "suggestions": out}
