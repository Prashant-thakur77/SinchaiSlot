from datetime import date

import pytest

from sinchai_jal.budget import DryRunGuard, WaterBudget, awd_irrigate, season_of


def test_budget_from_constants():
    b = WaterBudget.for_cluster()
    # 450 mm over 20 acres (8.09 ha) = about 36,400 m3
    assert 36000 < b.annual_m3 < 37000


def test_budget_never_exceeded():
    b = WaterBudget(annual_m3=1000)
    d = date(2024, 12, 1)
    cap = b.season_cap("rabi")
    b.record(d, cap - 1)
    with pytest.raises(ValueError):
        b.record(d, 5)
    assert b.remaining(d) == pytest.approx(1)


def test_alert_at_80_percent():
    b = WaterBudget(annual_m3=1000)
    d = date(2024, 4, 1)
    b.record(d, 0.81 * b.season_cap("zaid"))
    assert len(b.alerts) == 1 and b.alerts[0].scope == "zaid"
    b.record(d, 1)
    assert len(b.alerts) == 1


def test_category_scales_budget():
    assert WaterBudget.for_cluster(category="Critical").annual_m3 < WaterBudget.for_cluster(category="Safe").annual_m3


def test_seasons():
    assert season_of(date(2024, 1, 5)) == "rabi"
    assert season_of(date(2024, 5, 5)) == "zaid"
    assert season_of(date(2024, 8, 5)) == "kharif"


def test_dry_run_and_awd():
    g = DryRunGuard()
    assert g.underloaded(3.0, 1.0)
    assert not g.underloaded(3.0, 2.8)
    assert not g.underloaded(0.1, 0.0)
    assert awd_irrigate(-160, "mid") and not awd_irrigate(-100, "mid")
    assert awd_irrigate(-10, "initial")
