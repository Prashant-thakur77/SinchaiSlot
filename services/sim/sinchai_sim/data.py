"""Inputs for Prayogshala: actual PV, forecast PV quantiles and daily FAO-56 weather."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

from sinchai_devices.physics import default_array
from sinchai_planner import fao56
from sinchai_planner import forecast as F
from sinchai_schemas import constants as C

ROOT = Path(__file__).resolve().parents[3]
REPORTS = ROOT / "reports"
FC_CACHE = REPORTS / "cache" / "forecast_test_ghi.parquet"
FC_METRICS = REPORTS / "cache" / "forecast_metrics.json"


@lru_cache(maxsize=1)
def observations_ist() -> pd.DataFrame:
    df = pd.read_parquet(F.SNAP / "nasa_power_hourly.parquet")
    return df[df.index.year <= 2025]


@lru_cache(maxsize=1)
def pv_actual() -> pd.Series:
    o = observations_ist()
    return default_array().dc_power_kw(o["ghi"], o["temp_c"], o["wind_ms"])


def ensure_forecasts(refit: bool = False) -> tuple[pd.DataFrame, dict]:
    """Fit the forecaster on 2022-2023, predict held-out 2024-2025 (cached under reports/cache)."""
    if FC_CACHE.exists() and FC_METRICS.exists() and not refit:
        return pd.read_parquet(FC_CACHE), json.loads(FC_METRICS.read_text())
    FC_CACHE.parent.mkdir(parents=True, exist_ok=True)
    frame = F.build_frame()
    model = F.fit(frame)
    metrics = F.evaluate(frame, model)
    preds = F.test_predictions(frame, model)
    preds.to_parquet(FC_CACHE)
    FC_METRICS.write_text(json.dumps(metrics, indent=2))
    return preds, metrics


@lru_cache(maxsize=1)
def forecast_pv() -> pd.DataFrame:
    preds, _ = ensure_forecasts()
    o = observations_ist()
    idx = preds.index.tz_convert("Asia/Kolkata")
    arr = default_array()
    t = o["temp_c"].reindex(idx).ffill()
    w = o["wind_ms"].reindex(idx).ffill()
    out = {}
    for q in ("q10", "q50", "q90"):
        g = pd.Series(preds[q].to_numpy(), index=idx)
        out[q] = arr.dc_power_kw(g, t, w)
    return pd.DataFrame(out)


@lru_cache(maxsize=1)
def daily_weather() -> pd.DataFrame:
    return fao56.add_et0(fao56.daily_weather_from_hourly(observations_ist()), C.get("site_lat"))
