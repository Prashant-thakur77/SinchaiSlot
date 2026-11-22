"""Drive-as-meter: estimate delivered water from Altivar telemetry, calibrated against a flow meter.

Raw estimate: flow from the pump curve at the measured output frequency (RFR, affinity laws), cross
checked with the power the drive reports (OPR x nominal power). Where the two disagree strongly the
pump is not lifting water normally (dry run, blocked suction, worn impeller) and the estimate is
flagged instead of billed.

Calibration: an optional clamp-on or inline flow meter is read for a few sessions; a single
multiplicative factor k = sum(meter) / sum(estimate) is fitted by least squares through the origin,
with its relative standard error. After that the meter can be removed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .adapter import DriveTelemetry
from .physics import PumpModel, default_pump


@dataclass
class FlowEstimate:
    flow_m3h: float
    flow_from_speed: float
    flow_from_power: float
    consistent: bool
    k: float


@dataclass
class DriveMeter:
    pump: PumpModel = field(default_factory=default_pump)
    k: float = 1.0
    k_rse: float | None = None
    tolerance: float = 0.35
    samples: list[tuple[float, float]] = field(default_factory=list)  # (estimate m3, meter m3)

    def estimate(self, t: DriveTelemetry) -> FlowEstimate:
        n = t.freq_hz / self.pump.f_nom_hz
        q_speed = float(self.pump.flow_at_speed(n))
        q_power = float(self.pump.flow_for_power(t.power_kw))
        if q_speed <= 0:
            return FlowEstimate(0.0, 0.0, q_power, True, self.k)
        consistent = abs(q_power - q_speed) <= self.tolerance * q_speed
        q = q_speed if consistent else 0.0
        return FlowEstimate(round(q * self.k, 3), q_speed, q_power, consistent, self.k)

    def add_calibration(self, estimate_m3: float, meter_m3: float) -> None:
        if estimate_m3 > 0 and meter_m3 >= 0:
            self.samples.append((estimate_m3, meter_m3))
            self._fit()

    def _fit(self) -> None:
        x = np.array([s[0] for s in self.samples])
        y = np.array([s[1] for s in self.samples])
        self.k = float(x @ y / (x @ x))
        if len(x) > 1:
            resid = y - self.k * x
            se = np.sqrt(resid @ resid / (len(x) - 1) / (x @ x))
            self.k_rse = float(se / self.k) if self.k else None
