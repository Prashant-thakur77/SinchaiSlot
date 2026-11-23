"""Sentinel-2 crop-calendar classifier: synthetic series (offline) and the committed snapshot."""

from __future__ import annotations

import json
import math
from datetime import date, timedelta

import numpy as np
import pytest
from sinchai_data import sentinel as S

# Roughly every 10 days through one agricultural year, June 2024 to May 2025.
DATES = [date(2024, 6, 5) + timedelta(days=10 * i) for i in range(36)]


def _series(fn) -> np.ndarray:
    return np.array([fn(d) for d in DATES], dtype=np.float32)


def _bump(d: date, peak: date, width_days: float, height: float, base: float = 0.15) -> float:
    return base + height * math.exp(-(((d - peak).days / width_days) ** 2))


def paddy(d):  # kharif crop: peak late September, bare in rabi
    return _bump(d, date(2024, 9, 25), 35, 0.65)


def wheat(d):  # rabi crop: peak mid February, bare in monsoon
    return _bump(d, date(2025, 2, 10), 30, 0.62)


def double(d):
    return max(paddy(d), wheat(d))


def trees(d):
    return 0.70 + 0.08 * math.sin(d.toordinal() / 58.0)


def builtup(d):
    return 0.12 + 0.03 * math.sin(d.toordinal() / 40.0)


def water(d):
    return -0.15


def _codes(*fns, ndwi=None):
    stack = np.stack([_series(f) for f in fns], axis=1)  # (T, N)
    codes, _ = S.classify(stack, DATES, ndwi=ndwi)
    return [S.CODE_TO_CLASS.get(int(c), "no_data") for c in codes]


def test_each_phenology_maps_to_its_class():
    got = _codes(paddy, wheat, double, trees, builtup)
    assert got == ["kharif_paddy", "rabi_wheat_mustard", "double_cropped", "orchard_trees", "fallow_builtup"]


def test_water_by_negative_ndvi_and_positive_ndwi():
    ndwi = np.full((len(DATES), 2), 0.3, dtype=np.float32)
    ndwi[:, 1] = -0.4  # bare soil-like NDWI
    got = _codes(water, builtup, ndwi=ndwi)
    assert got == ["water", "fallow_builtup"]


def test_cloud_gaps_are_tolerated_and_empty_pixels_are_no_data():
    stack = np.stack([_series(paddy), _series(wheat), np.full(len(DATES), np.nan)], axis=1)
    rng = np.random.default_rng(0)
    gaps = rng.random(stack.shape) < 0.4
    gaps[[i for i, d in enumerate(DATES) if d == date(2024, 9, 23)], 0] = False  # keep one kharif peak look
    stack[gaps] = np.nan
    codes, _ = S.classify(stack, DATES)
    assert S.CODE_TO_CLASS[int(codes[0])] == "kharif_paddy"
    assert S.CODE_TO_CLASS[int(codes[1])] == "rabi_wheat_mustard"
    assert int(codes[2]) == S.NO_DATA_CODE


def test_weak_green_up_is_other():
    got = _codes(lambda d: _bump(d, date(2025, 1, 25), 30, 0.30))
    assert got == ["other_mixed"]


def test_shares_and_crop_mix_mapping():
    codes = np.array([1, 1, 2, 3, 4, 5, 6, 0], dtype=np.uint8)
    sh = S.class_shares(codes)
    assert math.isclose(sum(sh.values()), 1.0)
    assert math.isclose(sh["kharif_paddy"], 2 / 7)
    mix = S.crop_mix_from_shares(sh, rabi_split={"wheat": 0.65, "potato": 0.20})
    # cropland = 2 kharif-only + 1 rabi-only + 1 double = 4 pixels
    assert mix["crop_mix_kharif"] == {"paddy": 0.75, "fallow": 0.25}
    rabi = mix["crop_mix_rabi"]
    assert math.isclose(rabi["wheat"] + rabi["potato"], 0.5, abs_tol=1e-3)
    assert math.isclose(sum(rabi.values()), 1.0, abs_tol=1e-3)
    assert set(rabi) == {"wheat", "potato", "fallow"}


def test_wraparound_window():
    assert S._in_window(date(2025, 1, 20), S.RABI_WINDOW)
    assert S._in_window(date(2024, 12, 20), S.RABI_WINDOW)
    assert not S._in_window(date(2024, 9, 20), S.RABI_WINDOW)


def test_snapshot_exists_and_shares_sum_to_one():
    if not S.SHARES_PATH.exists():
        pytest.fail(f"missing snapshot {S.SHARES_PATH}; run python -m sinchai_data.sentinel")
    data = json.loads(S.SHARES_PATH.read_text())
    assert math.isclose(sum(data["shares"].values()), 1.0, abs_tol=1e-3)
    assert set(data["shares"]) == set(S.CLASSES)
    assert data["labels"] == {"imagery": "REAL", "classes": "DERIVED"}
    assert len(data["scenes"]) >= 8
    mix = S.crop_mix_from_s2()
    assert math.isclose(sum(mix["crop_mix_rabi"].values()), 1.0, abs_tol=1e-3)
    assert math.isclose(sum(mix["crop_mix_kharif"].values()), 1.0, abs_tol=1e-3)
