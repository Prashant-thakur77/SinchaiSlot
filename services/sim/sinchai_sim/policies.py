"""Policies A-D plus ablations used for the honest comparison.

A  Owner-only        pump serves the owner's plots only; everyone else buys diesel water.
B  Chakhaji          owner sells water by the hour, first come first served, owner first. PRIMARY BASELINE
C  Oorja-style       fixed per-m3 tariff, metered, FIFO; flour mill runs first-come when the pump is idle.
D  SinchaiSlot       forecast (P10/P50/P90) + stochastic MILP + energy router (mill, chaff cutter, battery
                     packs) + groundwater budget + fairness, with intraday re-planning.
Ablations
  C+loads            C with the same chaff cutter and battery packs, run greedily (isolates the planner)
  D-persistence      D planning on yesterday's sun instead of the forecast
  D-oracle           D planning on the actual sun (upper bound)
  D-noisy            D with a degraded forecast (stress test)
"""

from __future__ import annotations

import numpy as np
from sinchai_planner.optimizer import Loads, PlanInput, Request, Scenario, solve

from .engine import SLOT_HOURS, DayInputs, Policy, State


def _fifo(st: State, owner_first: bool = False) -> list[str]:
    items = sorted(st.pending.values(), key=lambda p: (not p.req.owner if owner_first else False, p.req.day, p.req.id))
    return [p.req.id for p in items if p.remaining > 1e-6]


class OwnerOnly(Policy):
    name = "A_owner_only"
    owner_only = True
    metered = True
    tariff_attr = "tariff_d"

    def slot_plan(self, st, di, t):
        if t not in st.cfg.operator_slots:
            return "idle", []
        return ("water", _fifo(st)) if st.pending else ("idle", [])


class Chakhaji(Policy):
    name = "B_chakhaji"
    hourly_billing = True
    metered = False
    owner_first = True

    def slot_plan(self, st, di, t):
        if t not in st.cfg.operator_slots:
            return "idle", []
        q = _fifo(st, owner_first=True)
        return ("water", q) if q else ("idle", [])


class OorjaStyle(Policy):
    name = "C_oorja_style"
    loads = frozenset({"mill"})
    tariff_attr = "tariff_c"

    def slot_plan(self, st, di, t):
        if t not in st.cfg.operator_slots:
            return "idle", []
        q = _fifo(st)
        if q and di.pv[t] > st.pump.p_cutoff_kw:
            return "water", q
        if st.mill_queue:
            return "mill", []
        return "idle", []


class OorjaPlusLoads(OorjaStyle):
    name = "C_plus_loads"
    loads = frozenset({"mill", "chaff", "battery"})

    def slot_plan(self, st, di, t):
        action, q = super().slot_plan(st, di, t)
        if action == "idle" and t in st.cfg.operator_slots and st.chaff_left_h > 0:
            return "chaff", []
        return action, q


class SinchaiSlot(Policy):
    """Policy D. Plans each morning on the forecast, re-plans intraday when the sun departs from it."""

    name = "D_sinchaislot"
    loads = frozenset({"mill", "chaff", "battery"})
    tariff_attr = "tariff_d"
    forecast = "model"  # "model" | "persistence" | "oracle" | "noisy"
    replan_threshold = 0.35
    max_replans = 3

    def __init__(self, forecast: str | None = None, noise_sd: float = 0.35, seed: int = 0):
        if forecast:
            self.forecast = forecast
            self.name = {"model": "D_sinchaislot", "persistence": "D_persistence", "oracle": "D_oracle",
                         "noisy": "D_noisy"}[forecast]
        self.noise_sd = noise_sd
        self.rng = np.random.default_rng(seed)
        self.plan_actions: dict[int, str] = {}
        self.plan_orders: dict[int, list[str]] = {}
        self.scen: list[Scenario] = []
        self.replans_today = 0

    # ---- forecast scenarios ----
    def _scenarios(self, di: DayInputs) -> list[Scenario]:
        if self.forecast == "oracle":
            return [Scenario("P50", 1.0, di.pv.copy())]
        if self.forecast == "persistence":
            return [Scenario("P50", 1.0, di.persist.copy())]
        q10, q50, q90 = di.q10.copy(), di.q50.copy(), di.q90.copy()
        if self.forecast == "noisy":
            f = float(np.exp(self.rng.normal(0, self.noise_sd)))
            q10, q50, q90 = q10 * f, q50 * f, q90 * f
        return [Scenario("P10", 0.3, q10), Scenario("P50", 0.4, q50), Scenario("P90", 0.3, q90)]

    def _solve(self, st: State, di: DayInputs, from_slot: int, frozen_action: dict[int, str] | None = None):
        cfg = st.cfg
        len(SLOT_HOURS)
        reqs = []
        pend = [p for p in st.pending.values() if p.remaining > 1e-6]
        for p in pend:
            waited = (di.day - p.req.day).days
            due = di.day >= p.req.deadline
            prio = 1.0 + 0.5 * waited + (1.5 if due else 0.0) + (0.5 if p.req.stage == "mid" else 0.0)
            reqs.append(Request(p.req.id, p.req.household, p.remaining, prio, due_today=due, tenant=p.req.tenant))
        p50 = next((s for s in self.scen if s.name == "P50"), self.scen[0]).pv_kw
        cap50 = float(np.sum(st.pump.flow_for_power(np.minimum(p50, st.pump.rated_kw))))
        tot = sum(r.remaining_m3 for r in reqs)
        fair = None
        if tot > 0:
            by_hh: dict[str, float] = {}
            for r in reqs:
                by_hh[r.household] = by_hh.get(r.household, 0.0) + r.remaining_m3
            fair = {h: 0.5 * min(v, cap50 * v / tot) for h, v in by_hh.items()}
        mill_kg = sum(k for k, _ in st.mill_queue)
        loads = Loads(
            mill_backlog_kg=mill_kg, mill_kwh_per_kg=cfg.mill_kwh_per_kg, mill_min_kw=cfg.mill_min_kw,
            mill_max_kw=cfg.mill_max_kw, mill_value_rs_per_kwh=cfg.mill_rs_per_kg / cfg.mill_kwh_per_kg,
            chaff_hours=st.chaff_left_h, chaff_kw=cfg.chaff_kw, chaff_value_rs_per_kwh=cfg.chaff_rs_per_h / cfg.chaff_kw,
            battery_kwh_demand=st.battery_left_kwh, battery_max_kw=cfg.battery_max_kw,
            battery_value_rs_per_kwh=cfg.pack_rs / cfg.pack_kwh,
        )
        scen = []
        for s in self.scen:
            pv = s.pv_kw.copy()
            pv[:from_slot] = 0
            scen.append(Scenario(s.name, s.prob, pv))
        frozen = {t: "idle" for t in range(from_slot)}
        if frozen_action:
            frozen.update(frozen_action)
        inp = PlanInput(
            slot_starts=[f"{di.day.isoformat()}T{h:02d}:30" for h in SLOT_HOURS], slot_h=1.0,
            scenarios=scen, requests=reqs, loads=loads,
            budget_remaining_m3=st.budget.remaining(di.day) if st.budget is not None else float("inf"),
            operator_slots=cfg.operator_slots, fair_m3=fair, frozen=frozen, time_limit_s=5.0, mip_rel_gap=5e-3,
        )
        plan = solve(inp, st.pump)
        st.solve_times.append(plan.solve_s)
        if st.budget is not None:
            planned = max(plan.total("water", s.name) for s in scen)
            if tot > 0 and planned >= st.budget.remaining(di.day) - 1e-3 and planned < tot - 1e-3:
                st.budget_bound_days += 1
        self.plan_actions = {}
        self.plan_orders = {}
        prio = {r.id: r.priority for r in reqs}
        planned_ids = [s.action[4:] for s in plan.slots if s.action.startswith("req:")]
        for sp in plan.slots:
            if sp.slot < from_slot:
                continue
            if sp.action.startswith("req:"):
                first = sp.action[4:]
                rest = sorted(set(planned_ids) - {first}, key=lambda i: -prio.get(i, 0))
                self.plan_actions[sp.slot] = "water"
                self.plan_orders[sp.slot] = [first, *rest]
            else:
                self.plan_actions[sp.slot] = sp.action
        return plan

    def begin_day(self, st, di):
        self.scen = self._scenarios(di)
        self.replans_today = 0
        self._solve(st, di, 0)

    def slot_plan(self, st, di, t):
        a = self.plan_actions.get(t, "idle")
        if a == "water":
            order = [i for i in self.plan_orders.get(t, []) if i in st.pending]
            return ("water", order) if order else ("idle", [])
        if a == "mill" and not st.mill_queue:
            return "idle", []
        return a, []

    def after_slot(self, st, di, t):
        """Nowcast check: if this hour's sun departed from P50, rescale the rest of the day and re-plan."""
        if self.forecast == "oracle" or t + 1 >= len(SLOT_HOURS) or self.replans_today >= self.max_replans:
            return
        p50 = next((s for s in self.scen if s.name == "P50"), self.scen[0]).pv_kw
        f, a = float(p50[t]), float(di.pv[t])
        if f < 0.5 and a < 0.5:
            return
        ratio = (a + 0.1) / (f + 0.1)
        if abs(ratio - 1) <= self.replan_threshold:
            return
        # Blend the observed ratio into the next hours, fading back to the forecast.
        w = np.zeros(len(SLOT_HOURS))
        for k in range(t + 1, len(SLOT_HOURS)):
            w[k] = 0.6 ** (k - t)
        mult = 1 + (np.clip(ratio, 0.1, 3.0) - 1) * w
        self.scen = [Scenario(s.name, s.prob, np.minimum(s.pv_kw * mult, st.cfg.pv_kwp)) for s in self.scen]
        frozen_next = {}
        if t + 1 < len(SLOT_HOURS):
            nxt = self.plan_actions.get(t + 1)
            if nxt == "water" and self.plan_orders.get(t + 1):
                frozen_next = {t + 1: f"req:{self.plan_orders[t + 1][0]}"}
            elif nxt in ("mill", "chaff"):
                frozen_next = {t + 1: nxt}
        if frozen_next and list(frozen_next.values())[0].startswith("req:") and \
                list(frozen_next.values())[0][4:] not in st.pending:
            frozen_next = {}
        self._solve(st, di, t + 1, frozen_next)
        self.replans_today += 1
        st.replans += 1


def all_policies(seed: int = 0) -> list[Policy]:
    return [OwnerOnly(), Chakhaji(), OorjaStyle(), SinchaiSlot()]
