"""Prayogshala engine: runs one policy for one year on one village, hour by hour.

Execution model shared by every policy (so differences come only from the policy):
  * hourly slots 06:30-17:30 IST; actual PV power from real NASA POWER irradiance
  * the pump delivers water from the pump curve at the available power and stops below cut-off
    (Altivar Solar low-light function); metered policies stop a booking when its need is met
  * secondary loads only use power the pump does not; the mill needs its minimum power
  * a request not fully served by its deadline buys the remainder from a diesel seller
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sinchai_devices.physics import PumpModel, default_pump
from sinchai_jal.budget import WaterBudget
from sinchai_schemas import constants as C

from .village import IrrRequest, Village

SLOT_HOURS = list(range(6, 18))  # IST hour labels; each slot is the hour starting at HH:30


@dataclass
class Config:
    pv_kwp: float = field(default_factory=lambda: C.get("pv_kwp"))
    tariff_d: float = field(default_factory=lambda: C.get("sinchaislot_tariff_rs_per_m3"))
    tariff_c: float = field(default_factory=lambda: C.get("oorja_style_tariff_rs_per_m3"))
    solar_rs_per_hour: float = field(default_factory=lambda: C.get("solar_water_rs_per_hour"))
    diesel_rs_per_hour: float = field(default_factory=lambda: C.get("diesel_water_rs_per_hour"))
    diesel_flow_m3h: float = field(default_factory=lambda: C.get("diesel_pump_flow_m3h"))
    diesel_l_per_h: float = field(default_factory=lambda: C.get("diesel_l_per_hour_5hp"))
    co2_per_l: float = field(default_factory=lambda: C.get("co2_kg_per_l_diesel"))
    mill_kg_per_day: float = field(default_factory=lambda: C.get("mill_demand_kg_per_day"))
    mill_kwh_per_kg: float = field(default_factory=lambda: C.get("mill_kwh_per_kg"))
    mill_max_kw: float = field(default_factory=lambda: C.get("mill_rated_kw"))
    mill_min_kw: float = 2.0
    mill_rs_per_kg: float = field(default_factory=lambda: C.get("mill_rs_per_kg"))
    chaff_kw: float = field(default_factory=lambda: C.get("chaff_cutter_kw"))
    chaff_h_per_day: float = field(default_factory=lambda: C.get("chaff_cutter_hours_per_day"))
    chaff_rs_per_h: float = field(default_factory=lambda: C.get("chaff_cutter_rs_per_hour"))
    pack_kwh: float = field(default_factory=lambda: C.get("battery_pack_kwh"))
    packs_per_day: float = field(default_factory=lambda: C.get("battery_packs_per_day"))
    pack_rs: float = field(default_factory=lambda: C.get("battery_pack_rs_per_charge"))
    battery_max_kw: float = 2.0
    op_start: int = field(default_factory=lambda: int(C.get("operator_start_hour")))
    op_end: int = field(default_factory=lambda: int(C.get("operator_end_hour")))

    @property
    def diesel_rs_per_m3(self) -> float:
        return self.diesel_rs_per_hour / self.diesel_flow_m3h

    @property
    def operator_slots(self) -> list[int]:
        return [i for i, h in enumerate(SLOT_HOURS) if self.op_start <= h < self.op_end]


@dataclass
class Pending:
    req: IrrRequest
    remaining: float
    first_water: date | None = None
    solar_m3: float = 0.0  # useful (<= need)
    pumped_m3: float = 0.0  # including over-application
    diesel_m3: float = 0.0
    paid_rs: float = 0.0
    hours_billed: float = 0.0


@dataclass
class DayInputs:
    day: date
    pv: np.ndarray  # actual kW per slot
    q10: np.ndarray
    q50: np.ndarray
    q90: np.ndarray
    persist: np.ndarray


@dataclass
class State:
    cfg: Config
    pump: PumpModel
    village: Village
    budget: WaterBudget | None
    pending: dict[str, Pending] = field(default_factory=dict)
    done: list[Pending] = field(default_factory=list)
    mill_queue: list[list[float]] = field(default_factory=list)  # [kg, age_days]
    chaff_left_h: float = 0.0
    battery_left_kwh: float = 0.0
    daily: list[dict] = field(default_factory=list)
    slot_log: list[dict] = field(default_factory=list)
    replans: int = 0
    solve_times: list[float] = field(default_factory=list)
    lost_mill_kg: float = 0.0
    budget_bound_days: int = 0

    # ---- daily accumulators ----
    def new_day(self) -> dict:
        return defaultdict(float)


class Policy:
    name = "base"
    loads = frozenset()  # subset of {"mill", "chaff", "battery"}
    metered = True
    hourly_billing = False
    owner_only = False
    owner_first = False
    tariff_attr = "tariff_d"

    def begin_day(self, st: State, di: DayInputs) -> None:  # noqa: B027
        pass

    def slot_plan(self, st: State, di: DayInputs, t: int) -> tuple[str, list[str]]:
        """Return (action, ordered request ids) for slot t. action in water|mill|chaff|idle."""
        raise NotImplementedError

    def after_slot(self, st: State, di: DayInputs, t: int) -> None:  # noqa: B027
        pass


# ---------------------------------------------------------------------------
# Slot execution
# ---------------------------------------------------------------------------

def _serve_water(st: State, pol: Policy, di: DayInputs, t: int, order: list[str], acc: dict) -> float:
    """Run the pump for one hour; return the fraction of the hour the pump was busy."""
    pv = float(di.pv[t])
    p_pump = min(pv, st.pump.rated_kw)
    q = float(st.pump.flow_for_power(p_pump))  # m3 in this hour
    if q <= 1e-6 or not order:
        return 0.0
    if pol.hourly_billing and q < 0.4 * st.pump.q_rated_m3h:
        # Nobody pays Rs/hour for a trickle: the owner only sells hours with decent flow.
        return 0.0
    budget_left = st.budget.remaining(di.day) if st.budget is not None else math.inf
    if budget_left <= 1e-6:
        return 0.0
    time_left = 1.0
    tariff = getattr(st.cfg, pol.tariff_attr)
    for rid in order:
        if time_left <= 1e-6:
            break
        pdg = st.pending.get(rid)
        if pdg is None or pdg.remaining <= 1e-6:
            continue
        cap = q * time_left
        if pol.hourly_billing:
            # Hour-sold water: the buyer pays for the whole hour and uses it.
            pumped = min(cap, budget_left)
            useful = min(pumped, pdg.remaining)
            used_time = time_left
            if not pdg.req.owner:
                pdg.paid_rs += st.cfg.solar_rs_per_hour * used_time
                pdg.hours_billed += used_time
        else:
            pumped = min(cap, pdg.remaining, budget_left)
            useful = pumped
            used_time = pumped / q
            if not pdg.req.owner:
                pdg.paid_rs += pumped * tariff
        if pumped <= 0:
            break
        pdg.remaining -= useful
        pdg.solar_m3 += useful
        pdg.pumped_m3 += pumped
        if pdg.first_water is None:
            pdg.first_water = di.day
        if st.budget is not None:
            st.budget.record(di.day, pumped)
            budget_left -= pumped
        acc["water_m3"] += pumped
        acc["useful_m3"] += useful
        acc["pump_kwh"] += p_pump * used_time
        time_left -= used_time
        st.slot_log.append({"day": di.day, "slot": t, "req": rid, "m3": pumped, "kwh": p_pump * used_time})
        if pdg.remaining <= 1e-6:
            st.done.append(st.pending.pop(rid))
        if pol.hourly_billing:
            break
    return 1.0 - time_left


def _run_mill(st: State, pv_kw: float, frac: float, acc: dict) -> float:
    """Run the mill for `frac` of the hour; return energy used (kWh)."""
    if pv_kw < st.cfg.mill_min_kw or frac <= 0:
        return 0.0
    e_cap = min(pv_kw, st.cfg.mill_max_kw) * frac
    need = sum(k for k, _ in st.mill_queue) * st.cfg.mill_kwh_per_kg
    e = min(e_cap, need)
    kg = e / st.cfg.mill_kwh_per_kg
    left = kg
    for item in st.mill_queue:
        take = min(item[0], left)
        item[0] -= take
        left -= take
    st.mill_queue = [i for i in st.mill_queue if i[0] > 1e-9]
    acc["mill_kwh"] += e
    acc["mill_kg"] += kg
    return e


def _run_chaff(st: State, pv_kw: float, frac: float, acc: dict) -> float:
    if pv_kw < st.cfg.chaff_kw or frac <= 0 or st.chaff_left_h <= 0:
        return 0.0
    h = min(frac, st.chaff_left_h)
    st.chaff_left_h -= h
    acc["chaff_h"] += h
    acc["chaff_kwh"] += st.cfg.chaff_kw * h
    return st.cfg.chaff_kw * h


def _charge(st: State, kwh_avail: float, acc: dict) -> None:
    e = min(kwh_avail, st.cfg.battery_max_kw, st.battery_left_kwh)
    if e > 0:
        st.battery_left_kwh -= e
        acc["battery_kwh"] += e


def run_day(st: State, pol: Policy, di: DayInputs, new_reqs: list[IrrRequest]) -> dict:
    cfg = st.cfg
    acc: dict = defaultdict(float)
    acc["day"] = di.day
    # Arrivals.
    for r in new_reqs:
        p = Pending(r, r.gross_m3)
        if pol.owner_only and not r.owner:
            p.diesel_m3 = r.gross_m3
            p.paid_rs = r.gross_m3 * cfg.diesel_rs_per_m3
            p.remaining = 0
            st.done.append(p)
            continue
        st.pending[r.id] = p
    if "mill" in pol.loads:
        st.mill_queue.append([cfg.mill_kg_per_day, 0])
    st.chaff_left_h = cfg.chaff_h_per_day if "chaff" in pol.loads else 0.0
    st.battery_left_kwh = cfg.packs_per_day * cfg.pack_kwh if "battery" in pol.loads else 0.0

    pol.begin_day(st, di)
    for t in range(len(SLOT_HOURS)):
        pv = float(di.pv[t])
        acc["pv_kwh"] += pv
        action, order = pol.slot_plan(st, di, t)
        busy = 0.0
        used = 0.0
        if action == "water":
            busy = _serve_water(st, pol, di, t, order, acc)
            used = min(pv, st.pump.rated_kw) * busy
        free = 1.0 - busy
        if action == "mill" or (action == "water" and "mill" in pol.loads and free > 0):
            # A booking that finishes mid-hour hands the rest of the hour to the mill.
            used += _run_mill(st, pv, free, acc)
        elif action == "chaff":
            used += _run_chaff(st, pv, free, acc)
        if "battery" in pol.loads:
            _charge(st, max(pv - used, 0.0), acc)
        pol.after_slot(st, di, t)

    # Deadlines: unmet need is bought from a diesel seller.
    for rid in list(st.pending):
        p = st.pending[rid]
        if di.day >= p.req.deadline:
            p.diesel_m3 += p.remaining
            p.paid_rs += p.remaining * cfg.diesel_rs_per_m3 if not p.req.owner else 0.0
            p.remaining = 0
            st.done.append(st.pending.pop(rid))
    # Mill grain waits one day, then goes to a diesel/grid mill elsewhere.
    for item in st.mill_queue:
        item[1] += 1
    st.lost_mill_kg += sum(k for k, a in st.mill_queue if a >= 2)
    st.mill_queue = [i for i in st.mill_queue if i[1] < 2]
    acc["battery_unmet_kwh"] = st.battery_left_kwh
    acc["useful_kwh"] = acc["pump_kwh"] + acc["mill_kwh"] + acc["chaff_kwh"] + acc["battery_kwh"]
    st.daily.append(dict(acc))
    return acc


# ---------------------------------------------------------------------------
# Year runner
# ---------------------------------------------------------------------------

@dataclass
class YearData:
    days: list[DayInputs]


def build_year_data(pv_actual: pd.Series, fc_pv: pd.DataFrame, start: date, end: date) -> YearData:
    """Slice hourly PV (kW) and forecast PV quantiles into per-day slot arrays."""
    days = []
    persist = pv_actual.shift(24)
    d = start
    while d <= end:
        idx = [pd.Timestamp(f"{d.isoformat()} {h:02d}:30", tz="Asia/Kolkata") for h in SLOT_HOURS]
        pv = pv_actual.reindex(idx).fillna(0).to_numpy()
        f = fc_pv.reindex(idx).fillna(0)
        days.append(DayInputs(d, pv, f["q10"].to_numpy(), f["q50"].to_numpy(), f["q90"].to_numpy(),
                              persist.reindex(idx).fillna(0).to_numpy()))
        d += timedelta(days=1)
    return YearData(days)


def run_year(pol: Policy, village: Village, reqs: list[IrrRequest], yd: YearData, cfg: Config | None = None,
             with_budget: bool = False) -> State:
    cfg = cfg or Config()
    st = State(cfg=cfg, pump=default_pump(), village=village,
               budget=WaterBudget.for_cluster(command_area_ha=village.area_ha) if with_budget else None)
    by_day: dict[date, list[IrrRequest]] = defaultdict(list)
    for r in reqs:
        by_day[r.day].append(r)
    for di in yd.days:
        run_day(st, pol, di, by_day.get(di.day, []))
    # Close anything still pending at year end as diesel (end-of-window truncation).
    for rid in list(st.pending):
        p = st.pending.pop(rid)
        p.diesel_m3 += p.remaining
        p.remaining = 0
        st.done.append(p)
    return st
