import numpy as np
import pandas as pd
import pytest

from sinchai_planner import fao56


def test_et0_matches_fao56_example_18():
    # FAO-56 Example 18 (Brussels, 6 July): tmax 21.5, tmin 12.3, RHmean derived,
    # u2 2.078 m/s, Rs 22.07 MJ/m2/day, lat 50.80 N, elevation 100 m -> ET0 = 3.9 mm/day.
    # The example gives ea = 1.409 kPa; with es = 1.997 kPa that is RHmean ~= 70.6 %.
    et0 = fao56.et0_penman_monteith(
        np.array([21.5]), np.array([12.3]), np.array([70.6]), np.array([2.078]),
        np.array([22.07]), np.array([187]), 50.80, 100.0,
    )
    assert et0[0] == pytest.approx(3.9, abs=0.15)


def test_extraterrestrial_radiation_example_8():
    # FAO-56 Example 8: 20 S on 3 September (doy 246) -> Ra = 32.2 MJ/m2/day.
    ra = fao56.extraterrestrial_radiation(-20.0, np.array([246]))
    assert ra[0] == pytest.approx(32.2, abs=0.2)


def test_kc_curve_shape():
    w = fao56.CROPS["wheat"]
    assert w.kc(0) == w.kc_ini
    i, d, m, _ = w.stages
    assert w.kc(i + d + 1) == w.kc_mid
    assert w.kc(w.length - 1) < w.kc_mid
    assert w.kc(w.length + 5) == 0.0


def _dry_daily(start: str, days: int, et0: float = 4.0) -> pd.DataFrame:
    idx = pd.date_range(start, periods=days, freq="D")
    return pd.DataFrame({"et0": et0, "rain_mm": 0.0}, index=idx)


def test_wheat_needs_several_irrigations_when_dry():
    daily = _dry_daily("2023-11-01", 200, et0=3.0)
    ev = fao56.simulate_plot(fao56.CROPS["wheat"], daily, 2023)
    assert 3 <= len(ev) <= 10
    taw = fao56.TAW_MM_PER_M * fao56.CROPS["wheat"].root_depth_m
    assert all(0 < e.net_mm <= taw for e in ev)


def test_rain_reduces_irrigation():
    dry = _dry_daily("2023-11-01", 200, et0=3.0)
    wet = dry.copy()
    wet["rain_mm"] = 3.0
    w = fao56.CROPS["wheat"]
    assert len(fao56.simulate_plot(w, wet, 2023)) < len(fao56.simulate_plot(w, dry, 2023))


def test_awd_saves_water_on_paddy():
    daily = _dry_daily("2023-06-20", 180, et0=4.0)
    p = fao56.CROPS["paddy"]
    cf = sum(e.net_mm for e in fao56.simulate_plot(p, daily, 2023, awd=False))
    awd = sum(e.net_mm for e in fao56.simulate_plot(p, daily, 2023, awd=True))
    assert awd < cf


def test_gross_m3():
    assert fao56.gross_m3(50, 0.2, 0.5) == pytest.approx(200.0)
