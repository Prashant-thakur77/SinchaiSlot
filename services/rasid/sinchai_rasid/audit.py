"""Rasid anomaly audit: physical rules plus an Isolation Forest over receipt features.

Rules
  R1 impossible water: more m3 per kWh than the pump curve allows at any speed (+15% tolerance)
  R2 energy with no booking: pump energy recorded in a slot with no water receipt
  R3 booking with no energy: a water receipt with water but ~zero energy
  R4 meter disagreement: flow meter and drive estimate differ by more than 20%
Statistical
  S1 Isolation Forest outlier on (m3/kWh, kWh/hour, duration, start hour)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
from sinchai_devices.physics import PumpModel, default_pump
from sklearn.ensemble import IsolationForest

from .ledger import Receipt


@dataclass
class Finding:
    receipt_id: str | None
    rule: str
    severity: str
    detail: str


def max_m3_per_kwh(pump: PumpModel) -> float:
    p = np.linspace(pump.p_cutoff_kw + 0.05, pump.rated_kw, 200)
    return float(np.max(pump.flow_for_power(p) / p))


def _hours(r: Receipt) -> float:
    return max((datetime.fromisoformat(r.end) - datetime.fromisoformat(r.start)).total_seconds() / 3600, 1e-6)


def audit(receipts: list[Receipt], pump_energy_slots: list[tuple[str, float]] | None = None,
          pump: PumpModel | None = None, contamination: float = 0.01) -> list[Finding]:
    pump = pump or default_pump()
    cap = max_m3_per_kwh(pump) * 1.15
    out: list[Finding] = []
    water = [r for r in receipts if r.kind == "water"]
    for r in water:
        if r.kwh > 0.05 and r.m3 / r.kwh > cap:
            out.append(Finding(r.receipt_id, "R1", "high", f"{r.m3 / r.kwh:.1f} m3/kWh exceeds pump limit {cap:.1f}"))
        if r.m3 > 1 and r.kwh < 0.05:
            out.append(Finding(r.receipt_id, "R3", "high", "water recorded with no pump energy"))
        if r.m3_meter is not None and r.m3 > 0 and abs(r.m3_meter - r.m3) / r.m3 > 0.2:
            out.append(Finding(r.receipt_id, "R4", "medium", f"meter {r.m3_meter:.1f} vs drive {r.m3:.1f} m3"))
    if pump_energy_slots:
        covered = {(r.start[:13]) for r in water}
        for start, kwh in pump_energy_slots:
            if kwh > 0.2 and start[:13] not in covered:
                out.append(Finding(None, "R2", "medium", f"{kwh:.2f} kWh pump energy at {start} with no booking"))
    if len(water) >= 50:
        X = np.array([[r.m3 / max(r.kwh, 1e-3), r.kwh / _hours(r), _hours(r),
                       datetime.fromisoformat(r.start).hour] for r in water])
        iso = IsolationForest(n_estimators=200, contamination=contamination, random_state=0).fit(X)
        flags = iso.predict(X)
        for r, f in zip(water, flags, strict=True):
            if f == -1:
                out.append(Finding(r.receipt_id, "S1", "low", "statistical outlier among receipts"))
    return out
