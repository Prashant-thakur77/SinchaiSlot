"""Physics shared by the drive simulator, the planner and the simulation.

PV array
    DC power from GHI using pvlib: Erbs decomposition, Hay-Davies transposition onto a fixed
    south-facing plane, Faiman cell temperature, linear temperature coefficient, system derate.

Pump
    A centrifugal pump driven by a variable speed drive, described by
      pump curve at speed ratio n:   H = H0 * n^2 - a * Q^2
      system curve:                  H = Hs + b * Q^2
    with the rated point (Q_r, H_r) on both curves at n = 1. Electrical input power at the operating
    point is rho*g*Q*H / eta_w2w. Below the speed at which H0*n^2 equals the static head Hs the pump
    delivers no water: this is the low-sun cut-off the planner has to respect.

All values come from `constants.yaml`.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pandas as pd
import pvlib
from sinchai_schemas import constants as C

RHO_G = 1000 * 9.81


@dataclass(frozen=True)
class PumpModel:
    rated_kw: float
    q_rated_m3h: float
    h_rated_m: float
    shutoff_head_ratio: float = 1.4  # H0 / H_rated, typical end-suction centrifugal pump
    static_head_ratio: float = 0.7  # Hs / H_rated
    eta_w2w: float = 0.45  # wire-to-water efficiency at the rated point (drive + motor + pump)
    f_nom_hz: float = 50.0

    @property
    def h0(self) -> float:
        return self.shutoff_head_ratio * self.h_rated_m

    @property
    def hs(self) -> float:
        return self.static_head_ratio * self.h_rated_m

    @property
    def a(self) -> float:
        return (self.h0 - self.h_rated_m) / self.q_rated_m3h**2

    @property
    def b(self) -> float:
        return (self.h_rated_m - self.hs) / self.q_rated_m3h**2

    @property
    def n_cutoff(self) -> float:
        return float(np.sqrt(self.hs / self.h0))

    def flow_at_speed(self, n: np.ndarray | float) -> np.ndarray:
        n = np.asarray(n, dtype=float)
        q2 = (self.h0 * n**2 - self.hs) / (self.a + self.b)
        return np.sqrt(np.clip(q2, 0, None))

    def head_at_flow(self, q: np.ndarray | float) -> np.ndarray:
        q = np.asarray(q, dtype=float)
        return self.hs + self.b * q**2

    def power_at_speed(self, n: np.ndarray | float) -> np.ndarray:
        """Electrical input power (kW) at speed ratio n.

        Hydraulic power at the operating point divided by wire-to-water efficiency, plus the
        no-flow churn power below cut-off (affinity law, P ~ n^3), so the curve is monotone.
        The rated electrical power is scaled to `rated_kw` at n = 1.
        """
        n = np.asarray(n, dtype=float)
        q = self.flow_at_speed(n)
        hyd_kw = RHO_G * (q / 3600) * self.head_at_flow(q) / 1000
        p_flow = hyd_kw / self.eta_w2w
        p_rated_raw = RHO_G * (self.q_rated_m3h / 3600) * self.h_rated_m / 1000 / self.eta_w2w
        churn = 0.35 * p_rated_raw * n**3
        p = np.maximum(p_flow, churn)
        return p * self.rated_kw / p_rated_raw

    @lru_cache(maxsize=1)  # noqa: B019 - frozen dataclass, small cache
    def _table(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        n = np.linspace(0, 1, 2001)
        p = np.maximum.accumulate(self.power_at_speed(n))
        return n, p, self.flow_at_speed(n)

    def speed_for_power(self, p_kw: np.ndarray | float) -> np.ndarray:
        """Speed ratio an MPPT drive settles at when `p_kw` of solar power is available."""
        n, p, _ = self._table()
        return np.interp(np.clip(p_kw, 0, self.rated_kw), p, n)

    def flow_for_power(self, p_kw: np.ndarray | float) -> np.ndarray:
        """Delivered flow (m3/h) for available power, the drive running at MPPT up to rated."""
        return self.flow_at_speed(self.speed_for_power(p_kw))

    @property
    def p_cutoff_kw(self) -> float:
        return float(self.power_at_speed(self.n_cutoff))

    def freq_hz(self, n: np.ndarray | float) -> np.ndarray:
        return np.asarray(n) * self.f_nom_hz


def default_pump() -> PumpModel:
    return PumpModel(
        rated_kw=C.get("pump_rated_kw"),
        q_rated_m3h=C.get("pump_rated_flow_m3h"),
        h_rated_m=C.get("pump_rated_head_m"),
    )


@dataclass(frozen=True)
class PVArray:
    kwp: float
    lat: float
    lon: float
    tilt_deg: float = 25.0
    azimuth_deg: float = 180.0
    derate: float = 0.80
    temp_coeff: float = -0.004

    def dc_power_kw(self, ghi: pd.Series, temp_c: pd.Series, wind_ms: pd.Series | None = None) -> pd.Series:
        """Hourly-mean DC power (kW) from hourly GHI (W/m2) indexed by tz-aware timestamps.

        NASA POWER hourly values are period averages labelled at the start of the hour, so solar
        geometry is evaluated at the middle of each hour.
        """
        times = ghi.index + pd.Timedelta(minutes=30)
        loc = pvlib.location.Location(self.lat, self.lon)
        sp = loc.get_solarposition(times)
        dni_extra = pvlib.irradiance.get_extra_radiation(times)
        g = pd.Series(ghi.to_numpy(), index=times).clip(lower=0)
        erbs = pvlib.irradiance.erbs(g, sp["zenith"], times)
        poa = pvlib.irradiance.get_total_irradiance(
            self.tilt_deg,
            self.azimuth_deg,
            sp["apparent_zenith"],
            sp["azimuth"],
            dni=erbs["dni"].fillna(0),
            ghi=g,
            dhi=erbs["dhi"].fillna(0),
            dni_extra=dni_extra,
            model="haydavies",
        )["poa_global"].fillna(0).clip(lower=0)
        t_air = pd.Series(temp_c.to_numpy(), index=times)
        ws = pd.Series(wind_ms.to_numpy(), index=times) if wind_ms is not None else 1.0
        t_cell = pvlib.temperature.faiman(poa, t_air, ws)
        p = self.kwp * poa / 1000 * (1 + self.temp_coeff * (t_cell - 25)) * self.derate
        p = p.clip(lower=0, upper=self.kwp)
        p.index = ghi.index
        return p


def default_array() -> PVArray:
    return PVArray(
        kwp=C.get("pv_kwp"),
        lat=C.get("site_lat"),
        lon=C.get("site_lon"),
        derate=C.get("pv_system_derate"),
        temp_coeff=C.get("pv_temp_coeff_per_c"),
    )
