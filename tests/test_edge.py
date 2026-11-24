"""Edge controller tests, including fully offline operation."""

from datetime import datetime, timedelta

import pytest
from sinchai_devices.adapter import InProcessAltivar
from sinchai_devices.altivar_model import AltivarModel
from sinchai_edge.controller import EdgeController, MemoryUplink, unlock_code

SECRET = b"test-secret"


class Clock:
    def __init__(self, t):
        self.t = t

    def mono(self):
        return (self.t - datetime(2024, 1, 1)).total_seconds()


def setup(tmp_path=None, pv=4.0, m3=10.0, budget=100.0, paid=False):
    clk = Clock(datetime(2024, 12, 10, 10, 0))
    model = AltivarModel(pv_kw=lambda t: pv, clock=clk.mono)
    up = MemoryUplink()
    ec = EdgeController("P1", InProcessAltivar(model), SECRET, up, state_dir=tmp_path)
    plan = {"pump_id": "P1", "version": 1, "budget_remaining_m3": budget, "slots": [
        {"start": "2024-12-10T10:00", "end": "2024-12-10T11:00", "kind": "water", "booking_id": "B1", "m3": m3,
         "paid": paid},
        {"start": "2024-12-10T11:00", "end": "2024-12-10T12:00", "kind": "mill"},
    ]}
    ec.receive_plan(plan)
    return ec, model, up, clk


def run(ec, clk, minutes, step_s=10):
    for _ in range(int(minutes * 60 / step_s)):
        clk.t += timedelta(seconds=step_s)
        ec.step(clk.t)


def test_unpaid_slot_does_not_run():
    ec, model, up, clk = setup()
    run(ec, clk, 5)
    assert model.state != "operation_enabled"
    assert ec.delivered_m3.get("B1", 0) == 0


def test_unlock_code_runs_and_stops_at_volume():
    ec, model, up, clk = setup(m3=10.0)
    code = unlock_code(SECRET, "P1", "B1", 10.0, 0)
    assert not ec.enter_code("B1", "000000000")
    assert ec.enter_code("B1", code)
    assert not ec.enter_code("B1", code)  # replay rejected
    run(ec, clk, 40)
    assert ec.delivered_m3["B1"] == pytest.approx(10.0, abs=0.6)
    done = [e for e in ec.events if e.get("type") == "slot_completed"]
    assert done and done[0]["m3"] > 9.0


def test_offline_operation_buffers_and_flushes(tmp_path):
    ec, model, up, clk = setup(tmp_path, paid=True, m3=8.0)
    up.connected = False
    run(ec, clk, 30)
    assert ec.delivered_m3["B1"] > 7.0
    assert len(ec.outbox) > 10 and not any(t.endswith("event") and p.get("type") == "slot_completed"
                                           for t, p in up.sent)
    up.connected = True
    ec.flush()
    assert len(ec.outbox) == 0
    assert any(p.get("type") == "slot_completed" for _, p in up.sent)


def test_plan_survives_restart(tmp_path):
    ec, model, up, clk = setup(tmp_path, paid=True)
    ec2 = EdgeController("P1", ec.drive, SECRET, MemoryUplink(), state_dir=tmp_path)
    ec2.load_cached_plan()
    assert ec2.plan and ec2.plan.version == 1 and ec2.plan.slots[0].paid


def test_budget_cutoff():
    ec, model, up, clk = setup(paid=True, m3=50.0, budget=5.0)
    run(ec, clk, 40)
    assert ec.delivered_m3["B1"] <= 5.5
    assert model.state != "operation_enabled"


def test_dry_run_cutoff():
    ec, model, up, clk = setup(paid=True, m3=50.0)
    run(ec, clk, 2)
    model.set_dry_run(True)
    run(ec, clk, 3)
    assert ec.tripped in ("dry_run", "ULF")
    assert any(e.get("type") in ("dry_run_cutoff", "drive_fault") for e in ec.events)
    assert model.state != "operation_enabled"


def test_older_plan_version_ignored():
    ec, model, up, clk = setup()
    ec.receive_plan({"pump_id": "P1", "version": 0, "budget_remaining_m3": 1, "slots": []})
    assert ec.plan.version == 1
