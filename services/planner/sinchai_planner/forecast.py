"""Quantile solar forecasting for Surya Planner.

Recipe:
  1. One LightGBM quantile model per weather source (ECMWF IFS, GFS, ICON), each using that source's
     forecast irradiance and cloud cover plus physics features (clear-sky irradiance, solar
     geometry, yesterday's observed clear-sky index).
  2. A quantile meta-model stacked on the out-of-fold base-model quantiles.
  3. Baselines: persistence (yesterday, same hour, with empirical residual quantiles) and
     climatology (same hour, +/- 15 days, from 2016-2023).

Training years 2022-2023, held-out test years 2024-2025 (docs/decisions/0002).
Target: NASA POWER hourly GHI (W/m2). Quantiles are converted to PV power by the PV model.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import pvlib

from sinchai_schemas import constants as C

SNAP = Path(__file__).resolve().parents[2] / "data" / "snapshots"
QUANTILES = (0.1, 0.5, 0.9)
SOURCES = ("ecmwf_ifs025", "gfs_seamless", "icon_seamless")
TRAIN_YEARS = (2022, 2023)
TEST_YEARS = (2024, 2025)
CLIM_YEARS = tuple(range(2016, 2024))


def load_observations() -> pd.DataFrame:
    df = pd.read_parquet(SNAP / "nasa_power_hourly.parquet")
    df.index = df.index.tz_convert("UTC")
    return df


def load_nwp() -> pd.DataFrame:
    om = pd.read_parquet(SNAP / "open_meteo_forecasts.parquet")
    om.index = om.index.tz_convert("UTC") - pd.Timedelta(minutes=30)
    return om[~om.index.duplicated()]


def physics_features(index: pd.DatetimeIndex) -> pd.DataFrame:
    loc = pvlib.location.Location(C.get("site_lat"), C.get("site_lon"), altitude=53)
    mid = index + pd.Timedelta(minutes=30)
    sp = loc.get_solarposition(mid)
    cs = loc.get_clearsky(mid, model="ineichen")
    f = pd.DataFrame(
        {
            "cs_ghi": cs["ghi"].to_numpy(),
            "zenith": sp["apparent_zenith"].to_numpy(),
            "azimuth": sp["azimuth"].to_numpy(),
            "doy": mid.day_of_year,
            "hour_ist": ((mid.hour * 60 + mid.minute + 330) // 60) % 24,
        },
        index=index,
    )
    return f


def build_frame() -> pd.DataFrame:
    obs = load_observations()
    nwp = load_nwp()
    idx = obs.index
    f = physics_features(idx)
    f["y"] = obs["ghi"]
    f["year"] = idx.year
    # Yesterday's observations (available at planning time the evening before).
    f["persist"] = obs["ghi"].shift(24)
    day = obs["ghi"].resample("D").sum()
    day_cs = f["cs_ghi"].resample("D").sum()
    kd = (day / day_cs.replace(0, np.nan)).shift(1)
    f["kt_yday"] = kd.reindex(idx.floor("D")).to_numpy()
    for s in SOURCES:
        sw = nwp.get(f"shortwave_radiation_{s}")
        cc = nwp.get(f"cloud_cover_{s}")
        pr = nwp.get(f"precipitation_{s}")
        for lag in (-1, 0, 1):
            f[f"sw_{s}_{lag}"] = sw.reindex(idx + pd.Timedelta(hours=lag)).to_numpy() if sw is not None else np.nan
        f[f"cc_{s}"] = cc.reindex(idx).to_numpy() if cc is not None else np.nan
        f[f"pr_{s}"] = pr.reindex(idx).to_numpy() if pr is not None else np.nan
        f[f"swday_{s}"] = (
            sw.resample("D").sum().reindex(idx.floor("D")).to_numpy() if sw is not None else np.nan
        )
    return f


COMMON = ["cs_ghi", "zenith", "azimuth", "doy", "hour_ist", "persist", "kt_yday"]


def source_features(s: str) -> list[str]:
    return COMMON + [f"sw_{s}_-1", f"sw_{s}_0", f"sw_{s}_1", f"cc_{s}", f"pr_{s}", f"swday_{s}"]


def _lgb(alpha: float) -> lgb.LGBMRegressor:
    return lgb.LGBMRegressor(
        objective="quantile",
        alpha=alpha,
        n_estimators=400,
        learning_rate=0.04,
        num_leaves=31,
        min_child_samples=30,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.9,
        verbose=-1,
    )


def pinball(y: np.ndarray, q: np.ndarray, alpha: float) -> float:
    d = y - q
    return float(np.mean(np.maximum(alpha * d, (alpha - 1) * d)))


def mean_pinball(y: np.ndarray, qs: dict[float, np.ndarray]) -> float:
    return float(np.mean([pinball(y, qs[a], a) for a in QUANTILES]))


def _sort_quantiles(qs: dict[float, np.ndarray], cap: np.ndarray | None = None) -> dict[float, np.ndarray]:
    arr = np.sort(np.vstack([qs[a] for a in QUANTILES]), axis=0)
    arr = np.clip(arr, 0, None)
    if cap is not None:
        arr = np.minimum(arr, cap * 1.1 + 5)
    return {a: arr[i] for i, a in enumerate(QUANTILES)}


@dataclass
class QuantileForecaster:
    base: dict[str, dict[float, lgb.LGBMRegressor]]
    meta: dict[float, lgb.LGBMRegressor]
    cqr_margin: float = 0.0  # conformal widening of P10/P90, in clear-sky-index units

    def predict_base(self, f: pd.DataFrame) -> pd.DataFrame:
        out = {}
        for s, models in self.base.items():
            for a, m in models.items():
                out[f"b_{s}_{a}"] = m.predict(f[source_features(s)])
        return pd.DataFrame(out, index=f.index)

    def predict(self, f: pd.DataFrame) -> dict[float, np.ndarray]:
        b = self.predict_base(f)
        x = pd.concat([b, f[["cs_ghi", "zenith", "hour_ist", "doy"]]], axis=1)
        qs = {a: m.predict(x) for a, m in self.meta.items()}
        if self.cqr_margin:
            widen = self.cqr_margin * f["cs_ghi"].to_numpy()
            qs[0.1] = qs[0.1] - widen
            qs[0.9] = qs[0.9] + widen
        qs = _sort_quantiles(qs, f["cs_ghi"].to_numpy())
        night = f["zenith"].to_numpy() >= 90
        for a in qs:
            qs[a][night] = 0.0
        return qs


def fit(frame: pd.DataFrame, n_folds: int = 4, calibrate: bool = True) -> QuantileForecaster:
    """Fit the stacked model on the training years.

    With `calibrate`, a conformalised quantile regression margin is learned first: the pipeline is
    fitted on 2022-01..2023-06 and the P10/P90 non-conformity scores are measured on 2023-07..12
    (inside the training years, never touching the test years). The margin is the 80% quantile of
    max(q10 - y, y - q90) in clear-sky-index units, giving finite-sample P10-P90 coverage.
    """
    margin = 0.0
    if calibrate:
        cal_cut = pd.Timestamp("2023-07-01", tz="UTC")
        early = frame[frame.index < cal_cut]
        m0 = fit(early, n_folds=n_folds, calibrate=False)
        cal = frame[(frame.index >= cal_cut) & frame["year"].isin(TRAIN_YEARS)]
        cal = cal[cal["y"].notna() & (cal["zenith"] < 90) & (cal["cs_ghi"] > 20)]
        qs = m0.predict(cal)
        cs = cal["cs_ghi"].to_numpy()
        y = cal["y"].to_numpy()
        score = np.maximum(qs[0.1] - y, y - qs[0.9]) / cs
        n = len(score)
        margin = float(np.quantile(score, min(1.0, 0.8 * (n + 1) / n)))
    tr = frame[frame["year"].isin(TRAIN_YEARS) & frame["y"].notna() & (frame["zenith"] < 90)]
    # Out-of-fold base predictions grouped by month blocks, so the meta-model sees honest inputs.
    months = tr.index.year * 12 + tr.index.month
    folds = months % n_folds
    oof = pd.DataFrame(index=tr.index)
    for s in SOURCES:
        feats = source_features(s)
        for a in QUANTILES:
            col = np.full(len(tr), np.nan)
            for k in range(n_folds):
                m = _lgb(a).fit(tr.loc[folds != k, feats], tr.loc[folds != k, "y"])
                col[folds == k] = m.predict(tr.loc[folds == k, feats])
            oof[f"b_{s}_{a}"] = col
    base = {s: {a: _lgb(a).fit(tr[source_features(s)], tr["y"]) for a in QUANTILES} for s in SOURCES}
    xm = pd.concat([oof, tr[["cs_ghi", "zenith", "hour_ist", "doy"]]], axis=1)
    meta = {a: _lgb(a).fit(xm, tr["y"]) for a in QUANTILES}
    return QuantileForecaster(base=base, meta=meta, cqr_margin=max(margin, 0.0))


def climatology_quantiles(frame: pd.DataFrame, target_index: pd.DatetimeIndex) -> dict[float, np.ndarray]:
    hist = frame[frame["year"].isin(CLIM_YEARS)][["y", "doy", "hour_ist"]].dropna()
    grid = {}
    for h in range(24):
        hh = hist[hist["hour_ist"] == h]
        for d in range(1, 367):
            dd = np.minimum(np.abs(hh["doy"] - d), 366 - np.abs(hh["doy"] - d))
            vals = hh.loc[dd <= 15, "y"].to_numpy()
            grid[(h, d)] = np.quantile(vals, QUANTILES) if len(vals) else np.zeros(len(QUANTILES))
    t = frame.loc[target_index]
    arr = np.array([grid[(int(h), int(d))] for h, d in zip(t["hour_ist"], t["doy"], strict=True)])
    return {a: arr[:, i] for i, a in enumerate(QUANTILES)}


def persistence_quantiles(frame: pd.DataFrame, target_index: pd.DatetimeIndex) -> dict[float, np.ndarray]:
    tr = frame[frame["year"].isin(CLIM_YEARS) & (frame["zenith"] < 90)].dropna(subset=["y", "persist"])
    # Multiplicative residual quantiles on the clear-sky-normalised scale, by hour.
    ratio = (tr["y"] + 1) / (tr["persist"] + 1)
    qr = ratio.groupby(tr["hour_ist"]).quantile(list(QUANTILES)).unstack()
    t = frame.loc[target_index]
    out = {}
    for a in QUANTILES:
        r = qr[a].reindex(t["hour_ist"]).to_numpy()
        out[a] = np.clip((t["persist"].to_numpy() + 1) * r - 1, 0, None)
    return _sort_quantiles(out, t["cs_ghi"].to_numpy())


def evaluate(frame: pd.DataFrame, model: QuantileForecaster) -> dict:
    te = frame[frame["year"].isin(TEST_YEARS) & frame["y"].notna() & (frame["zenith"] < 90)]
    te = te.dropna(subset=["persist"])
    y = te["y"].to_numpy()
    res = {}
    for name, qs in {
        "sinchaislot_meta": model.predict(te),
        "persistence": persistence_quantiles(frame, te.index),
        "climatology": climatology_quantiles(frame, te.index),
    }.items():
        cover = float(np.mean((y >= qs[0.1]) & (y <= qs[0.9])))
        res[name] = {
            "pinball_w_m2": round(mean_pinball(y, qs), 2),
            "pinball_by_quantile": {str(a): round(pinball(y, qs[a], a), 2) for a in QUANTILES},
            "p10_p90_coverage": round(cover, 3),
            "mae_p50_w_m2": round(float(np.mean(np.abs(y - qs[0.5]))), 2),
        }
    # Per-source base models, to show the value of combining sources.
    b = model.predict_base(te)
    for s in SOURCES:
        qs = _sort_quantiles({a: b[f"b_{s}_{a}"].to_numpy() for a in QUANTILES})
        res[f"base_{s}"] = {"pinball_w_m2": round(mean_pinball(y, qs), 2)}
    m = res["sinchaislot_meta"]["pinball_w_m2"]
    res["skill_vs_persistence"] = round(1 - m / res["persistence"]["pinball_w_m2"], 3)
    res["skill_vs_climatology"] = round(1 - m / res["climatology"]["pinball_w_m2"], 3)
    res["cqr_margin_clearsky_index"] = round(model.cqr_margin, 4)
    res["n_test_hours"] = int(len(te))
    res["train_years"] = list(TRAIN_YEARS)
    res["test_years"] = list(TEST_YEARS)
    return res


def test_predictions(frame: pd.DataFrame, model: QuantileForecaster) -> pd.DataFrame:
    """Hourly P10/P50/P90 GHI for every hour of the held-out years (night = 0)."""
    te = frame[frame["year"].isin(TEST_YEARS)].copy()
    qs = model.predict(te)
    out = pd.DataFrame({f"q{int(a * 100)}": qs[a] for a in QUANTILES}, index=te.index)
    out["obs"] = te["y"]
    out["persist"] = te["persist"]
    return out
