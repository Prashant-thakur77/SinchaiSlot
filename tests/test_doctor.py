import json
from pathlib import Path

import numpy as np
import pandas as pd
from sinchai_devices.doctor import PumpCondition, PumpDoctor, Thresholds
from sinchai_devices.physics import default_pump

REPORTS = Path(__file__).resolve().parents[1] / "reports"


def test_healthy_condition_matches_the_pump_model():
    n = np.linspace(0, 1, 21)
    assert np.allclose(PumpCondition().power_at(n), default_pump().power_at_speed(n))


def test_signatures_point_opposite_ways():
    n = np.array([0.9, 0.95])
    healthy = PumpCondition().power_at(n)
    assert (PumpCondition(friction=1.15).power_at(n) > healthy).all()
    assert (PumpCondition(extra_head_m=4).power_at(n) < healthy).all()


def _hours(sun: float = 1.0, friction: float = 1.0, head: float = 0.0) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01 10:00", periods=120 * 4, freq="h", tz="Asia/Kolkata")
    idx = pd.DatetimeIndex([pd.Timestamp("2025-01-01 10:00", tz="Asia/Kolkata") + pd.Timedelta(days=i // 4, hours=i % 4) for i in range(len(idx))])
    late = np.arange(len(idx)) // 4 >= 90
    kw, hz = np.zeros(len(idx)), np.zeros(len(idx))
    for i in range(len(idx)):
        c = PumpCondition(head if late[i] else 0.0, friction if late[i] else 1.0)
        kw[i] = 3.0 * (sun if late[i] else 1.0)
        hz[i] = c.speed_for(kw[i]) * 50
    return pd.DataFrame({"freq_hz": hz, "power_kw": kw, "peer_kw": 3.0}, index=idx)


def test_each_fault_is_named():
    doc = PumpDoctor(Thresholds(0.09, 0.07, 0.07))
    for kwargs, want in (({}, None), ({"sun": 0.8}, "panels"), ({"friction": 1.15}, "friction"), ({"head": 4.0}, "water")):
        a = doc.first_alert(doc.scores(doc.daily_ratios(_hours(**kwargs))))
        assert (a[1] if a else None) == want


def test_no_neighbour_means_no_panel_verdict():
    h = _hours(sun=0.8)
    h["peer_kw"] = np.nan
    doc = PumpDoctor()
    assert doc.scores(doc.daily_ratios(h))["panels"].isna().all()


def test_published_report_is_consistent():
    r = json.loads((REPORTS / "doctor.json").read_text())
    assert r["trials"] == sum(v["trials"] for v in r["by_kind"].values())
    assert r["found"] >= r["right_cause"] > r["portal_found"]
    assert sum(sum(c.values()) for c in r["confusion"].values()) == r["trials"]


def test_scale_report_covers_the_pilot():
    r = json.loads((REPORTS / "scale.json").read_text())
    s = {d["name"]: d for d in r["districts"]}
    assert "Samastipur" in s and len(s) >= 12
    assert all(1000 < d["pv_kwh_per_kwp"] < 1600 for d in s.values())
