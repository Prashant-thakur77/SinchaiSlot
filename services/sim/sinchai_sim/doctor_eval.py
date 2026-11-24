"""Measure Pump Doctor on real weather with injected faults. Run: python -m sinchai_sim.doctor_eval

Each trial is a cluster of three pumps under the same real sun (NASA POWER): one may develop a fault,
two are neighbours with their own dust, wash days and running hours. Alert thresholds and every design
choice come from 2022-2023; the published scores are from 2024-2025.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sinchai_devices.doctor import PumpCondition, PumpDoctor, Thresholds

from .data import REPORTS, observations_ist, pv_actual

KINDS = ("panels_dust", "panels_shade", "friction", "water")
CLASS = {"panels_dust": "panels", "panels_shade": "panels", "friction": "friction", "water": "water"}
FALSE_ALARMS_PER_YEAR = 0.25
RATES = {"natural_soiling_per_day": 0.002, "fault_soiling_per_day": 0.008, "shade_loss": 0.20,
         "friction_ramp": 0.15, "water_drop_m": 4.0, "ramp_days": 45, "seasonal_swing_m": 3.0,
         "rain_wash_mm": 5.0, "routine_wash_days": 14, "run_probability": 0.6,
         "cloud_difference_between_pumps": 0.08, "pump_curve_slope_error": 0.10, "daily_head_noise_m": 0.4,
         "module_mismatch": 0.04}


def inputs() -> pd.DataFrame:
    return pd.DataFrame({"pv": pv_actual(), "rain": observations_ist()["rain_mm"]}).loc["2022":]


def telemetry(df: pd.DataFrame, rng: np.random.Generator, kind: str | None, onset: int,
              severity: float = 1.0) -> pd.DataFrame:
    """One simulated pump over the period. `onset` is a day number; kind None means no fault."""
    days = df.index.floor("D")
    codes, uniq = pd.factorize(days)
    n = len(uniq)
    d = np.arange(n)
    rain = df["rain"].groupby(codes).sum().to_numpy()
    ramp = np.clip((d - onset) / RATES["ramp_days"], 0, 1) if kind else np.zeros(n)
    soil, s = np.zeros(n), 0.0
    phase = int(rng.integers(RATES["routine_wash_days"]))
    for i in range(n):
        dusty = kind == "panels_dust" and i >= onset
        s += RATES["fault_soiling_per_day"] * severity if dusty else RATES["natural_soiling_per_day"]
        if rain[i] >= RATES["rain_wash_mm"] or (not dusty and (i + phase) % RATES["routine_wash_days"] == 0):
            s = 0.0
        soil[i] = min(s, 0.35)
    shade = severity * RATES["shade_loss"] * (kind == "panels_shade") * (d >= onset)
    doy = pd.DatetimeIndex(uniq).dayofyear.to_numpy()
    # Water deepest at the end of May, shallowest at the end of September.
    head = RATES["seasonal_swing_m"] / 2 * np.cos(2 * np.pi * (doy - 150) / 365) + rng.normal(0, RATES["daily_head_noise_m"], n)
    head = head + (severity * RATES["water_drop_m"] * ramp if kind == "water" else 0)
    friction = 1 + (severity * RATES["friction_ramp"] * ramp if kind == "friction" else np.zeros(n))
    pv = df["pv"].to_numpy() * (1 - soil[codes]) * (1 - shade[codes])
    pv = pv * rng.normal(1, RATES["module_mismatch"]) * rng.normal(1, RATES["cloud_difference_between_pumps"], len(df)).clip(0.6, 1.4)
    slope = rng.normal(0, RATES["pump_curve_slope_error"])  # this pump's curve is not the catalogue curve
    kw, hz = np.zeros(len(df)), np.zeros(len(df))
    for i in range(n):
        m = slice(*np.searchsorted(codes, [i, i + 1]))
        c = PumpCondition(float(head[i]), float(friction[i]))
        p = pv[m]
        s_ = c.speed_for(p)
        on = s_ > c.cutoff_n
        kw[m] = np.where(on, np.minimum(p, c.power_at(s_)), 0) * (1 + slope * (s_ - 0.9))
        hz[m] = np.where(on, s_ * 50, 0)
    ran = rng.random(len(df)) < RATES["run_probability"]
    kw = np.round(kw * rng.normal(1, 0.02, len(df)) / 3.7 * 100) / 100 * 3.7  # OPR resolution: 1 % of nominal
    out = pd.DataFrame({"freq_hz": np.round(hz, 1), "power_kw": kw}, index=df.index)
    return out[ran & (hz > 0)]


def cluster(df: pd.DataFrame, rng: np.random.Generator, kind: str | None, onset: int,
            severity: float = 1.0) -> pd.DataFrame:
    """Telemetry of the watched pump with the mean sun-limited power of neighbours running that hour."""
    peers = []
    for _ in range(2):
        t = telemetry(df, rng, None, 0)
        peers.append(t["power_kw"].where(t["freq_hz"] < 49.5))
    own = telemetry(df, rng, kind, onset, severity)
    own["peer_kw"] = pd.concat(peers, axis=1).mean(axis=1).reindex(own.index)
    return own


def portal_scores(hours: pd.DataFrame, baseline_d: int = 30) -> pd.Series:
    """Named baseline: a monitoring portal that compares recent daily kWh with the previous month."""
    e = hours["power_kw"].groupby(hours.index.floor("D")).sum()
    recent = e.rolling(10, min_periods=10).mean()
    return (1 - recent / e.rolling(baseline_d, min_periods=baseline_d).mean().shift(10)).iloc[baseline_d:]


def run(trials: int = 60, seed: int = 11, score_on: str = "test", severity: float = 1.0) -> dict:
    df = inputs()
    tune, test = df.loc["2022":"2023"], df.loc["2024":"2025"]
    if score_on == "tune":
        test = tune
    doc = PumpDoctor()
    years_tune, years_test = len(tune) / 8766, len(test) / 8766
    rng = np.random.default_rng(seed)

    mx = {k: [] for k in ("panels", "friction", "water", "portal")}
    for _ in range(40):
        h = cluster(tune, rng, None, 0)
        s = doc.scores(doc.daily_ratios(h))
        for k in ("panels", "friction", "water"):
            mx[k].append(s[k].max())
        mx["portal"].append(portal_scores(h).max())
    # Each detector may wrongly alert on this share of fault-free pumps over the tuning period.
    q = 1 - FALSE_ALARMS_PER_YEAR * years_tune / 3
    th = Thresholds(**{k: float(np.quantile(mx[k], q)) for k in ("panels", "friction", "water")})
    portal_th = float(np.quantile(mx["portal"], 1 - FALSE_ALARMS_PER_YEAR * years_tune))
    doc.thresholds = th

    fa, pfa = 0, 0
    for _ in range(trials):
        h = cluster(test, rng, None, 0)
        fa += doc.first_alert(doc.scores(doc.daily_ratios(h))) is not None
        pfa += bool((portal_scores(h) >= portal_th).any())

    by_kind, confusion = {}, {c: {} for c in ("panels", "friction", "water")}
    n_days = test.index.floor("D").nunique()
    tz = test.index.tz
    for kind in KINDS:
        found, right, days, portal_found, early = 0, 0, [], 0, 0
        for _ in range(trials):
            onset = int(rng.integers(90, n_days - 100))
            t0 = pd.Timestamp(test.index[0].date(), tz=tz) + pd.Timedelta(days=onset)
            h = cluster(test, rng, kind, onset, severity)
            s = doc.scores(doc.daily_ratios(h))
            # A pump already alerting before the fault starts is counted apart, not as a detection.
            if doc.first_alert(s[s.index < t0]) is not None:
                early += 1
                continue
            a = doc.first_alert(s[s.index < t0 + pd.Timedelta(days=60)], after=t0)
            label = a[1] if a else "missed"
            confusion[CLASS[kind]][label] = confusion[CLASS[kind]].get(label, 0) + 1
            if a:
                found += 1
                right += a[1] == CLASS[kind]
                days.append((a[0] - t0).days)
            p = portal_scores(h)
            p_pre, p_post = p[p.index < t0], p[(p.index >= t0) & (p.index < t0 + pd.Timedelta(days=60))]
            portal_found += bool((p_post >= portal_th).any() and not (p_pre >= portal_th).any())
        n = trials - early
        by_kind[kind] = {"trials": n, "already_alerting": early, "found_in_60_days": round(found / n, 3),
                         "right_cause": round(right / n, 3), "portal_found_in_60_days": round(portal_found / n, 3),
                         "median_days": float(np.median(days)) if days else None}
    tot = sum(v["trials"] for v in by_kind.values())

    def avg(key: str) -> float:
        return round(sum(v[key] * v["trials"] for v in by_kind.values()) / tot, 3)

    return {"generated_by": "python -m sinchai_sim.doctor_eval",
            "label": "SIMULATED pumps with injected faults on REAL weather; thresholds set on 2022-2023, scored on 2024-2025",
            "assumptions": RATES, "thresholds": {k: round(v, 4) for k, v in vars(th).items()},
            "trials": tot, "healthy_pumps": trials, "target_false_alarms_per_pump_year": FALSE_ALARMS_PER_YEAR,
            "false_alarms_per_pump_year_at_least": round(fa / trials / years_test, 3),
            "portal_false_alarms_per_pump_year_at_least": round(pfa / trials / years_test, 3),
            "found": avg("found_in_60_days"), "right_cause": avg("right_cause"),
            "portal_found": avg("portal_found_in_60_days"), "by_kind": by_kind, "confusion": confusion,
            "not_seen": "Dust falling on every pump of the cluster at once; a leak inside the pump that leaves motor power unchanged; that needs the optional flow meter."}


def example(seed: int = 5) -> dict:
    """One pump per fault for the screen: daily ratios around the onset."""
    df = inputs().loc["2024":"2025"]
    rep = json.loads((REPORTS / "doctor.json").read_text())
    doc = PumpDoctor(Thresholds(**rep["thresholds"]))
    out = {}
    for kind in (None, *KINDS):
        h = cluster(df, np.random.default_rng(seed), kind, 290)
        s = doc.scores(doc.daily_ratios(h)).loc["2024-09-01":"2025-01-31"]
        a = doc.first_alert(s, after=pd.Timestamp("2024-10-17", tz=df.index.tz)) if kind else None
        out[kind or "healthy"] = {"onset": "2024-10-17" if kind else None,
                                  "alert": {"day": str(a[0].date()), "cause": a[1]} if a else None,
                                  "days": [str(x.date()) for x in s.index],
                                  **{k: [None if pd.isna(v) else round(float(v), 4) for v in s[k]] for k in ("panels", "friction", "water")}}
    return out


if __name__ == "__main__":
    r = run()
    half = run(severity=0.5)
    r["half_size_faults"] = {k: half[k] for k in ("found", "right_cause", "portal_found", "by_kind")}
    (REPORTS / "doctor.json").write_text(json.dumps(r, indent=2))
    r["example"] = example()
    (REPORTS / "doctor.json").write_text(json.dumps(r, indent=2))
    print(json.dumps({k: v for k, v in r.items() if k != "example"}, indent=2))
