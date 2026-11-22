"""Optimiser invariants (PLAN.md 13.5): budget never exceeded, minimum shares met, no double booking,
crop-water caps respected, secondary loads never take energy the pump needs."""

import numpy as np
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from sinchai_planner.optimizer import Loads, PlanInput, Request, scenarios_from_quantiles, solve
from sinchai_planner.replan import explain_diff, replan

SLOTS = [f"2024-12-10T{h:02d}:00" for h in range(6, 18)]


def bell(peak: float) -> np.ndarray:
    return np.clip(np.sin(np.linspace(0.05, np.pi - 0.05, 12)), 0, None) * peak


def make_input(n_req=6, budget=1e9, peak=4.2, mill=100.0, battery=4.0, seed=0, due=0):
    rng = np.random.default_rng(seed)
    reqs = [
        Request(id=f"r{i}", household=f"h{i % max(n_req - 1, 1)}", remaining_m3=float(rng.uniform(10, 120)),
                priority=float(rng.uniform(1, 3)), due_today=i < due, tenant=bool(i % 2))
        for i in range(n_req)
    ]
    scen = scenarios_from_quantiles(bell(peak * 0.5), bell(peak * 0.85), bell(peak))
    loads = Loads(mill_backlog_kg=mill, mill_value_rs_per_kwh=40, chaff_hours=1, chaff_value_rs_per_kwh=25,
                  battery_kwh_demand=battery, battery_value_rs_per_kwh=20)
    return PlanInput(slot_starts=SLOTS, slot_h=1.0, scenarios=scen, requests=reqs, loads=loads,
                     budget_remaining_m3=budget, operator_slots=list(range(1, 11)))


def check_invariants(inp: PlanInput, plan) -> None:
    assert plan.status in ("Optimal", "Time limit reached", "Empty")
    # No double booking: each slot has exactly one action.
    assert len({s.slot for s in plan.slots}) == len(plan.slots)
    for s in plan.scenarios if hasattr(plan, "scenarios") else inp.scenarios:
        total = sum(sp.water_m3[s.name] for sp in plan.slots)
        assert total <= inp.budget_remaining_m3 + 1e-6, "budget exceeded"
    for r in inp.requests:
        for sc in inp.scenarios:
            assert plan.served_m3.get(r.id, {}).get(sc.name, 0.0) <= r.remaining_m3 + 1e-6, "crop cap exceeded"
    for sp in plan.slots:
        if sp.action != "idle" and sp.action.startswith("req:"):
            assert sp.slot in inp.operator_slots
        for sc in inp.scenarios:
            used = sp.mill_kwh[sc.name] + sp.chaff_kwh[sc.name] + sp.battery_kwh[sc.name]
            assert used <= sp.pv_kw[sc.name] * inp.slot_h + 1e-6, "loads exceed solar"
    # Minimum share: every due household with any usable slot gets at least one slot.
    due_hh = {r.household for r in inp.requests if r.due_today}
    served_hh = {sp.household for sp in plan.slots if sp.household}
    usable = sum(1 for t in inp.operator_slots if inp.scenarios[-1].pv_kw[t] > 0.6)
    if len(due_hh) <= usable:
        assert due_hh <= served_hh, "due household got no slot"


def test_basic_plan_routes_surplus_to_loads():
    inp = make_input(n_req=2)
    plan = solve(inp)
    check_invariants(inp, plan)
    assert plan.total("water") > 0
    assert plan.total("battery") > 0 or plan.total("mill") > 0


def test_water_comes_before_mill():
    # Plenty of water demand: the mill must not take a sunny slot from a booking.
    inp = make_input(n_req=12, mill=1000)
    plan = solve(inp)
    check_invariants(inp, plan)
    assert all(s.action != "mill" for s in plan.slots if s.pv_kw["P50"] > 3.0)


def test_budget_binds():
    inp = make_input(n_req=8, budget=50.0)
    plan = solve(inp)
    check_invariants(inp, plan)
    assert max(plan.total("water", s.name) for s in inp.scenarios) <= 50.0 + 1e-6


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    n_req=st.integers(0, 14),
    budget=st.floats(0, 800),
    peak=st.floats(0.3, 5.0),
    mill=st.floats(0, 400),
    battery=st.floats(0, 8),
    seed=st.integers(0, 1000),
    due=st.integers(0, 8),
)
def test_invariants_random(n_req, budget, peak, mill, battery, seed, due):
    inp = make_input(n_req=n_req, budget=budget, peak=peak, mill=mill, battery=battery, seed=seed,
                     due=min(due, n_req))
    check_invariants(inp, solve(inp))


def test_replan_freezes_and_explains():
    inp = make_input(n_req=6)
    plan = solve(inp)
    cloud = [s for s in inp.scenarios]
    from sinchai_planner.optimizer import Scenario
    new = []
    for s in cloud:
        pv = s.pv_kw.copy()
        pv[7:10] *= 0.2  # cloud 13:00-15:59
        new.append(Scenario(s.name, s.prob, pv))
    p2 = replan(inp, plan, now_slot=5, new_scenarios=new, freeze_min=60)
    # Slots before now and inside the freeze window are unchanged.
    for t in range(0, 6):
        assert p2.slots[t].action == plan.slots[t].action
    diff = explain_diff(plan, p2, inp.scenarios, new)
    assert all(c.reason_en and c.reason_hi for c in diff)
