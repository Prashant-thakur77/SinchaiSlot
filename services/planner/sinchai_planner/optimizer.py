"""Surya Planner optimiser: two-stage stochastic MILP solved with HiGHS.

First stage (decided now, executed by the edge controller):
    x[r,t]   booking r is served by the pump in slot t                      (binary)
    m[t]     flour mill runs in slot t                                       (binary)
    c[t]     chaff cutter runs in slot t                                     (binary)
Second stage (per solar scenario s = P10 / P50 / P90):
    w[r,t,s] water delivered to booking r in slot t, m3                     (continuous)
    em[t,s]  energy to the mill, kWh;  ec[t,s] chaff cutter;  eb[t,s] battery packs
    sh[h,s]  shortfall of household h below its fair volume                (continuous)

Constraints
    * one machine on the solar bus per slot (pump booking, mill or chaff cutter)
    * water per slot <= pump flow at the scenario's solar power (pump curve, MPPT)
    * per-booking crop-water cap (FAO-56 remaining need)
    * cluster water budget, hard, in every scenario
    * households with a booking due today get at least one slot (hard, pre-checked feasible)
    * secondary loads only use what the pump leaves; mill and cutter need their minimum power
    * operator hours for attended machines (pump starts, mill, cutter); battery charging unattended

Objective (expectation over scenarios, lexicographic weights so water always comes first):
    W_WATER * sum(priority_r * w) - W_FAIR * sum(sh) + Rs value of mill, cutter and battery energy
    - small start penalty to keep each farmer's slots contiguous.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import highspy
import numpy as np
from sinchai_devices.physics import PumpModel, default_pump

W_WATER = 1000.0  # per m3 * priority; dominates any secondary-load value per kWh
W_FAIR = 500.0  # per m3 of fair-share shortfall
START_PENALTY = 150.0  # keeps each farmer's water in one contiguous block


@dataclass
class Request:
    id: str
    household: str
    remaining_m3: float
    priority: float = 1.0  # FAO-56 stress weighting, >= 1 when urgent
    due_today: bool = False
    tenant: bool = False
    allowed_slots: list[int] | None = None  # None = all operator slots


@dataclass
class Scenario:
    name: str
    prob: float
    pv_kw: np.ndarray  # mean available DC power per slot


@dataclass
class Loads:
    mill_backlog_kg: float = 0.0
    mill_kwh_per_kg: float = 0.07
    mill_min_kw: float = 2.0
    mill_max_kw: float = 3.7
    mill_value_rs_per_kwh: float = 0.0
    chaff_hours: float = 0.0
    chaff_kw: float = 1.5
    chaff_value_rs_per_kwh: float = 0.0
    battery_kwh_demand: float = 0.0
    battery_max_kw: float = 2.0
    battery_value_rs_per_kwh: float = 0.0


@dataclass
class PlanInput:
    slot_starts: list[str]  # ISO times, for labelling
    slot_h: float
    scenarios: list[Scenario]
    requests: list[Request]
    loads: Loads = field(default_factory=Loads)
    budget_remaining_m3: float = float("inf")
    operator_slots: list[int] | None = None  # slots in Saur Mitra working hours
    fair_m3: dict[str, float] | None = None  # household -> fair volume today
    frozen: dict[int, str] | None = None  # slot -> "req:<id>" | "mill" | "chaff" | "idle"
    time_limit_s: float = 10.0
    mip_rel_gap: float = 1e-3


@dataclass
class SlotPlan:
    slot: int
    start: str
    action: str  # "req:<id>" | "mill" | "chaff" | "idle"
    household: str | None
    water_m3: dict[str, float]  # per scenario
    mill_kwh: dict[str, float]
    chaff_kwh: dict[str, float]
    battery_kwh: dict[str, float]
    pv_kw: dict[str, float]


@dataclass
class Plan:
    slots: list[SlotPlan]
    served_m3: dict[str, dict[str, float]]  # request -> scenario -> m3
    status: str
    objective: float
    mip_gap: float
    solve_s: float
    n_binaries: int
    n_constraints: int

    def expected_water(self, req_id: str) -> float:
        return self.served_m3.get(req_id, {}).get("P50", 0.0)

    def assignment(self) -> dict[int, str]:
        return {s.slot: s.action for s in self.slots}

    def total(self, kind: str, scenario: str = "P50") -> float:
        attr = {"water": "water_m3", "mill": "mill_kwh", "chaff": "chaff_kwh", "battery": "battery_kwh"}[kind]
        return float(sum(getattr(s, attr)[scenario] for s in self.slots))


def solve(inp: PlanInput, pump: PumpModel | None = None) -> Plan:
    pump = pump or default_pump()
    T = len(inp.slot_starts)
    S = inp.scenarios
    R = [r for r in inp.requests if r.remaining_m3 > 1e-6]
    L = inp.loads
    dt = inp.slot_h
    op = set(range(T)) if inp.operator_slots is None else set(inp.operator_slots)
    frozen = inp.frozen or {}

    pv = {s.name: np.asarray(s.pv_kw, dtype=float) for s in S}
    qcap = {n: pump.flow_for_power(p) * dt for n, p in pv.items()}  # m3 per slot
    pump_kw = {n: np.minimum(p, pump.rated_kw) for n, p in pv.items()}
    best_q = np.max(np.vstack(list(qcap.values())), axis=0)

    h = highspy.Highs()
    h.silent()
    h.setOptionValue("time_limit", inp.time_limit_s)
    h.setOptionValue("mip_rel_gap", inp.mip_rel_gap)
    h.setOptionValue("random_seed", 1)
    h.setOptionValue("threads", 1)

    obj = 0
    n_bin = 0
    x: dict[tuple[int, int], object] = {}
    for i, r in enumerate(R):
        allowed = set(r.allowed_slots) if r.allowed_slots is not None else set(range(T))
        for t in range(T):
            ub = 1.0 if (t in allowed and t in op and best_q[t] > 1e-6) else 0.0
            fz = frozen.get(t)
            if fz is not None:
                ub = 1.0 if fz == f"req:{r.id}" else 0.0
            lb = 1.0 if (fz == f"req:{r.id}" and ub > 0) else 0.0
            if ub > 0:
                x[i, t] = h.addVariable(lb=lb, ub=ub, type=highspy.HighsVarType.kInteger)
                n_bin += 1

    def _mach(kind: str, ok) -> dict[int, object]:
        nonlocal n_bin
        out = {}
        for t in range(T):
            fz = frozen.get(t)
            allowed = ok(t) and t in op
            if fz is not None:
                allowed = fz == kind
            if allowed:
                out[t] = h.addVariable(lb=1.0 if fz == kind else 0.0, ub=1, type=highspy.HighsVarType.kInteger)
                n_bin += 1
        return out

    mill_on = L.mill_backlog_kg > 0
    m = _mach("mill", lambda t: mill_on and max(p[t] for p in pv.values()) >= L.mill_min_kw)
    c = _mach("chaff", lambda t: L.chaff_hours > 0 and max(p[t] for p in pv.values()) >= L.chaff_kw)

    # One machine per slot on the solar bus.
    for t in range(T):
        terms = [x[i, t] for i in range(len(R)) if (i, t) in x]
        if t in m:
            terms.append(m[t])
        if t in c:
            terms.append(c[t])
        if len(terms) > 1:
            h.addConstr(sum(terms) <= 1)
    if c:
        h.addConstr(sum(c.values()) * dt <= L.chaff_hours)

    # Households with a booking due today get at least one slot.
    due_hh: dict[str, list[int]] = {}
    for i, r in enumerate(R):
        if r.due_today:
            due_hh.setdefault(r.household, []).append(i)
    usable = sum(1 for t in range(T) if t in op and best_q[t] > 1e-6 and t not in frozen)
    guaranteed = sorted(due_hh, key=lambda hh: (not any(R[i].tenant for i in due_hh[hh]), hh))[:usable]
    for hh in guaranteed:
        terms = [x[i, t] for i in due_hh[hh] for t in range(T) if (i, t) in x]
        if terms:
            h.addConstr(sum(terms) >= 1)

    # Contiguity: penalise starts.
    for i in range(len(R)):
        for t in range(T):
            if (i, t) not in x:
                continue
            st = h.addVariable(lb=0, ub=1)
            prev = x.get((i, t - 1))
            h.addConstr(st >= x[i, t] - (prev if prev is not None else 0))
            obj = obj - START_PENALTY * st

    w: dict[tuple[int, int, str], object] = {}
    served: dict[tuple[int, str], object] = {}
    em: dict[tuple[int, str], object] = {}
    ec: dict[tuple[int, str], object] = {}
    eb: dict[tuple[int, str], object] = {}
    for s in S:
        n = s.name
        for (i, t), xv in x.items():
            wv = h.addVariable(lb=0, ub=float(qcap[n][t]))
            h.addConstr(wv <= float(qcap[n][t]) * xv)
            w[i, t, n] = wv
        for i, r in enumerate(R):
            terms = [w[i, t, n] for t in range(T) if (i, t, n) in w]
            if not terms:
                continue
            sv = h.addVariable(lb=0, ub=r.remaining_m3)
            h.addConstr(sv == sum(terms))
            served[i, n] = sv
            obj = obj + s.prob * W_WATER * r.priority * sv
        all_w = [w[k] for k in w if k[2] == n]
        if all_w and np.isfinite(inp.budget_remaining_m3):
            h.addConstr(sum(all_w) <= max(inp.budget_remaining_m3, 0.0))
        # Fair-share shortfall.
        if inp.fair_m3:
            for hh, fair in inp.fair_m3.items():
                idx = [i for i, r in enumerate(R) if r.household == hh]
                terms = [served[i, n] for i in idx if (i, n) in served]
                if not terms or fair <= 0:
                    continue
                sh = h.addVariable(lb=0, ub=fair)
                h.addConstr(sh >= fair - sum(terms))
                obj = obj - s.prob * W_FAIR * sh
        # Secondary loads use what the pump leaves.
        for t in range(T):
            p = float(pv[n][t])
            pump_on = [x[i, t] for i in range(len(R)) if (i, t) in x]
            avail = p * dt
            pump_draw = float(pump_kw[n][t]) * dt
            if t in m:
                cap = min(p, L.mill_max_kw) * dt if p >= L.mill_min_kw else 0.0
                v = h.addVariable(lb=0, ub=cap)
                h.addConstr(v <= cap * m[t])
                em[t, n] = v
                obj = obj + s.prob * L.mill_value_rs_per_kwh * v
            if t in c:
                cap = L.chaff_kw * dt if p >= L.chaff_kw else 0.0
                v = h.addVariable(lb=0, ub=cap)
                h.addConstr(v <= cap * c[t])
                ec[t, n] = v
                obj = obj + s.prob * L.chaff_value_rs_per_kwh * v
            if L.battery_kwh_demand > 0 and p > 0:
                v = h.addVariable(lb=0, ub=min(L.battery_max_kw, p) * dt)
                used = []
                if pump_on:
                    used.append(pump_draw * sum(pump_on))
                if (t, n) in em:
                    used.append(em[t, n])
                if (t, n) in ec:
                    used.append(ec[t, n])
                if used:
                    h.addConstr(v + sum(used) <= avail)
                eb[t, n] = v
                obj = obj + s.prob * L.battery_value_rs_per_kwh * v
        mill_terms = [em[t, n] for t in range(T) if (t, n) in em]
        if mill_terms:
            h.addConstr(sum(mill_terms) <= L.mill_backlog_kg * L.mill_kwh_per_kg)
        bat_terms = [eb[t, n] for t in range(T) if (t, n) in eb]
        if bat_terms:
            h.addConstr(sum(bat_terms) <= L.battery_kwh_demand)

    h.maximize(obj)
    t0 = time.perf_counter()
    h.run()
    solve_s = time.perf_counter() - t0
    status = h.modelStatusToString(h.getModelStatus())
    info = h.getInfo()
    sol = h.getSolution()
    vals = np.asarray(sol.col_value)

    def val(v) -> float:
        return float(vals[v.index]) if v is not None else 0.0

    slots: list[SlotPlan] = []
    for t in range(T):
        action, hh = "idle", None
        for i, r in enumerate(R):
            if (i, t) in x and val(x[i, t]) > 0.5:
                action, hh = f"req:{r.id}", r.household
        if t in m and val(m[t]) > 0.5:
            action = "mill"
        if t in c and val(c[t]) > 0.5:
            action = "chaff"
        wd = {}
        for s in S:
            wd[s.name] = sum(val(w[i, t, s.name]) for i in range(len(R)) if (i, t, s.name) in w)
        slots.append(
            SlotPlan(
                slot=t,
                start=inp.slot_starts[t],
                action=action,
                household=hh,
                water_m3=wd,
                mill_kwh={s.name: val(em.get((t, s.name))) for s in S},
                chaff_kwh={s.name: val(ec.get((t, s.name))) for s in S},
                battery_kwh={s.name: val(eb.get((t, s.name))) for s in S},
                pv_kw={s.name: float(pv[s.name][t]) for s in S},
            )
        )
    served_out = {r.id: {s.name: val(served.get((i, s.name))) for s in S} for i, r in enumerate(R)}
    return Plan(
        slots=slots,
        served_m3=served_out,
        status=status,
        objective=float(h.getObjectiveValue()),
        mip_gap=float(info.mip_gap),
        solve_s=solve_s,
        n_binaries=n_bin,
        n_constraints=int(h.getNumRow()),
    )


def scenarios_from_quantiles(q10: np.ndarray, q50: np.ndarray, q90: np.ndarray) -> list[Scenario]:
    """Three-point scenario set from P10/P50/P90 power (Swanson's rule weights 0.3/0.4/0.3)."""
    return [
        Scenario("P10", 0.3, np.asarray(q10)),
        Scenario("P50", 0.4, np.asarray(q50)),
        Scenario("P90", 0.3, np.asarray(q90)),
    ]
