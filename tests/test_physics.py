import numpy as np
import pandas as pd
import pytest
from sinchai_devices.physics import default_array, default_pump


def test_pump_rated_point():
    p = default_pump()
    assert float(p.flow_at_speed(1.0)) == pytest.approx(p.q_rated_m3h, rel=1e-6)
    assert float(p.power_at_speed(1.0)) == pytest.approx(p.rated_kw, rel=1e-6)


def test_pump_cutoff_no_flow_below():
    p = default_pump()
    assert float(p.flow_at_speed(p.n_cutoff - 0.01)) == 0.0
    assert float(p.flow_at_speed(p.n_cutoff + 0.05)) > 0.0
    assert 0 < p.p_cutoff_kw < p.rated_kw


def test_flow_monotone_in_power():
    p = default_pump()
    pw = np.linspace(0, p.rated_kw, 200)
    q = p.flow_for_power(pw)
    assert np.all(np.diff(q) >= -1e-9)
    assert q[0] == 0.0
    assert q[-1] == pytest.approx(p.q_rated_m3h, rel=1e-3)


def test_pv_clear_noon_near_rated():
    a = default_array()
    idx = pd.date_range("2024-03-20 06:00", periods=12, freq="h", tz="Asia/Kolkata")
    ghi = pd.Series(np.sin(np.linspace(0.1, np.pi - 0.1, 12)) * 900, index=idx)
    temp = pd.Series(25.0, index=idx)
    p = a.dc_power_kw(ghi, temp)
    assert p.max() <= a.kwp
    assert 3.0 < p.max() < 5.0
    assert p.iloc[0] < p.max()
