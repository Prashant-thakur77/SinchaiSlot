"""FAO-56 crop water requirement engine.

Implements, from FAO Irrigation and Drainage Paper 56 (Allen et al. 1998):
  * daily reference evapotranspiration ET0 by the Penman-Monteith equation (eq. 6),
    with net radiation from measured solar radiation (eqs. 21-40),
  * single crop coefficient Kc curves (chapter 6, tables 11-12),
  * a root-zone soil water balance (chapter 8, eqs. 82-86) that triggers irrigation when
    depletion exceeds readily available water (RAW = p * TAW).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

SIGMA = 4.903e-9  # Stefan-Boltzmann, MJ K-4 m-2 day-1


def _svp(t: float | np.ndarray) -> float | np.ndarray:
    """Saturation vapour pressure kPa at temperature t (C), eq. 11."""
    return 0.6108 * np.exp(17.27 * t / (t + 237.3))


def extraterrestrial_radiation(lat_deg: float, doy: np.ndarray) -> np.ndarray:
    """Ra in MJ m-2 day-1, eqs. 21-25."""
    phi = math.radians(lat_deg)
    dr = 1 + 0.033 * np.cos(2 * np.pi / 365 * doy)
    delta = 0.409 * np.sin(2 * np.pi / 365 * doy - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(delta), -1, 1))
    return (24 * 60 / np.pi) * 0.0820 * dr * (
        ws * np.sin(phi) * np.sin(delta) + np.cos(phi) * np.cos(delta) * np.sin(ws)
    )


def et0_penman_monteith(
    tmax: np.ndarray,
    tmin: np.ndarray,
    rh_mean: np.ndarray,
    u2: np.ndarray,
    rs: np.ndarray,
    doy: np.ndarray,
    lat_deg: float,
    elevation_m: float,
) -> np.ndarray:
    """Daily ET0 (mm/day). rs in MJ m-2 day-1, u2 in m/s at 2 m."""
    tmean = (tmax + tmin) / 2
    p = 101.3 * ((293 - 0.0065 * elevation_m) / 293) ** 5.26  # eq. 7
    gamma = 0.665e-3 * p  # eq. 8
    delta = 4098 * _svp(tmean) / (tmean + 237.3) ** 2  # eq. 13
    es = (_svp(tmax) + _svp(tmin)) / 2  # eq. 12
    ea = rh_mean / 100 * es  # eq. 19
    ra = extraterrestrial_radiation(lat_deg, doy)
    rso = (0.75 + 2e-5 * elevation_m) * ra  # eq. 37
    rns = (1 - 0.23) * rs  # eq. 38
    rel = np.clip(rs / np.where(rso > 0, rso, np.nan), 0.25, 1.0)
    rnl = (
        SIGMA
        * ((tmax + 273.16) ** 4 + (tmin + 273.16) ** 4)
        / 2
        * (0.34 - 0.14 * np.sqrt(np.maximum(ea, 0)))
        * (1.35 * rel - 0.35)
    )  # eq. 39
    rn = rns - rnl
    num = 0.408 * delta * rn + gamma * 900 / (tmean + 273) * u2 * (es - ea)
    den = delta + gamma * (1 + 0.34 * u2)
    return np.maximum(num / den, 0.0)


def daily_weather_from_hourly(hourly: pd.DataFrame) -> pd.DataFrame:
    """Aggregate NASA POWER hourly data (columns ghi, temp_c, rh, wind_ms, rain_mm) to daily."""
    d = pd.DataFrame(
        {
            "tmax": hourly["temp_c"].resample("D").max(),
            "tmin": hourly["temp_c"].resample("D").min(),
            "rh_mean": hourly["rh"].resample("D").mean(),
            "u2": hourly["wind_ms"].resample("D").mean(),
            "rs": hourly["ghi"].resample("D").sum() * 3600 / 1e6,  # Wh/m2 -> MJ/m2
            "rain_mm": hourly["rain_mm"].resample("D").sum(),
        }
    )
    d.index = d.index.tz_localize(None).normalize()
    return d.dropna()


def add_et0(daily: pd.DataFrame, lat_deg: float, elevation_m: float = 53.0) -> pd.DataFrame:
    d = daily.copy()
    d["et0"] = et0_penman_monteith(
        d["tmax"].to_numpy(),
        d["tmin"].to_numpy(),
        d["rh_mean"].to_numpy(),
        d["u2"].to_numpy(),
        d["rs"].to_numpy(),
        d.index.dayofyear.to_numpy(),
        lat_deg,
        elevation_m,
    )
    return d


# ---------------------------------------------------------------------------
# Crops: FAO-56 tables 11 (stage lengths) and 12 (Kc), Bihar sowing windows.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Crop:
    key: str
    name_en: str
    name_hi: str
    season: str
    sow_month: int
    sow_day: int
    stages: tuple[int, int, int, int]  # initial, development, mid, late (days)
    kc_ini: float
    kc_mid: float
    kc_end: float
    root_depth_m: float
    p_depletion: float  # fraction of TAW that can be depleted before stress (table 22)
    is_paddy: bool = False
    yield_t_per_ha: float = 0.0  # used for m3 per kg grain; see constants notes

    @property
    def length(self) -> int:
        return sum(self.stages)

    def kc(self, day_after_sowing: int) -> float:
        i, d, m, late = self.stages
        t = day_after_sowing
        if t < 0 or t >= self.length:
            return 0.0
        if t < i:
            return self.kc_ini
        if t < i + d:
            return self.kc_ini + (t - i) / d * (self.kc_mid - self.kc_ini)
        if t < i + d + m:
            return self.kc_mid
        return self.kc_mid + (t - i - d - m) / late * (self.kc_end - self.kc_mid)

    def sowing_date(self, year: int) -> date:
        return date(year, self.sow_month, self.sow_day)


CROPS: dict[str, Crop] = {
    # Wheat, rabi. FAO-56 table 11 (wheat, India) and table 12 spring wheat Kc.
    "wheat": Crop("wheat", "Wheat", "गेहूँ", "rabi", 11, 20, (15, 25, 50, 30), 0.4, 1.15, 0.3, 1.0, 0.55,
                  yield_t_per_ha=3.0),
    # Spring / zaid maize. Table 12 maize (grain).
    "maize": Crop("maize", "Maize", "मक्का", "zaid", 2, 10, (20, 35, 40, 30), 0.3, 1.2, 0.35, 0.9, 0.55,
                  yield_t_per_ha=4.0),
    # Kharif paddy, transplanted. Table 12 rice.
    "paddy": Crop("paddy", "Paddy", "धान", "kharif", 7, 1, (30, 30, 60, 30), 1.05, 1.2, 0.75, 0.5, 0.2,
                  is_paddy=True, yield_t_per_ha=3.5),
    # Potato as the rabi vegetable. Table 12 potato.
    "potato": Crop("potato", "Potato", "आलू", "rabi", 10, 25, (25, 30, 45, 30), 0.5, 1.15, 0.75, 0.4, 0.35,
                   yield_t_per_ha=20.0),
    # Summer vegetables (okra / gourds). Table 12 small vegetables.
    "veg_summer": Crop("veg_summer", "Summer vegetables", "सब्ज़ी", "zaid", 3, 1, (20, 30, 40, 20), 0.5, 1.05,
                       0.9, 0.5, 0.4, yield_t_per_ha=10.0),
}

# Loam soil: total available water per metre of root zone (FAO-56 table 19 range 0.11-0.20).
TAW_MM_PER_M = 150.0
PADDY_PERCOLATION_MM_DAY = 3.0  # continuous flooding percolation + seepage (assumption)
PADDY_POND_TARGET_MM = 50.0
PADDY_PUDDLING_MM = 150.0  # land preparation / pre-saturation (assumption)
AWD_THRESHOLD_MM = -150.0  # field water level below surface that triggers AWD irrigation (IRRI "safe AWD")


@dataclass
class IrrigationEvent:
    day: date
    net_mm: float
    crop: str
    stage: str


def stage_name(crop: Crop, das: int) -> str:
    i, d, m, _ = crop.stages
    if das < i:
        return "initial"
    if das < i + d:
        return "development"
    if das < i + d + m:
        return "mid"
    return "late"


def simulate_plot(
    crop: Crop,
    daily: pd.DataFrame,
    year: int,
    awd: bool = False,
) -> list[IrrigationEvent]:
    """Run the FAO-56 root-zone water balance for one crop season and return irrigation events.

    `daily` must have columns et0 and rain_mm indexed by date. Effective rain is rain minus
    runoff above 50 mm/day (simple cap, adequate for flat alluvial fields).
    """
    sow = crop.sowing_date(year)
    events: list[IrrigationEvent] = []
    taw = TAW_MM_PER_M * crop.root_depth_m
    raw = crop.p_depletion * taw
    depletion = 0.3 * taw  # start moderately moist after land preparation
    pond = 0.0
    level = 0.0  # paddy field water level relative to surface, mm (negative = below)
    if crop.is_paddy:
        events.append(IrrigationEvent(sow - timedelta(days=3), PADDY_PUDDLING_MM, crop.key, "puddling"))
        pond = PADDY_POND_TARGET_MM
        level = pond
    for das in range(crop.length):
        day = sow + timedelta(days=das)
        ts = pd.Timestamp(day)
        if ts not in daily.index:
            continue
        et0 = float(daily.at[ts, "et0"])
        rain = float(daily.at[ts, "rain_mm"])
        peff = min(rain, 50.0)
        etc = crop.kc(das) * et0
        if crop.is_paddy:
            level += peff - etc - PADDY_PERCOLATION_MM_DAY
            level = min(level, 100.0)  # bund height spill
            late = das >= crop.length - 15  # drain before harvest
            trigger = (AWD_THRESHOLD_MM if awd and stage_name(crop, das) != "initial" else 0.0)
            if not late and level < trigger:
                need = PADDY_POND_TARGET_MM - level if not awd else PADDY_POND_TARGET_MM - level
                need = min(need, PADDY_POND_TARGET_MM + abs(AWD_THRESHOLD_MM))
                events.append(IrrigationEvent(day, need, crop.key, stage_name(crop, das)))
                level += need
            continue
        depletion = max(depletion - peff + etc, 0.0)
        depletion = min(depletion, taw)
        if depletion > raw and das < crop.length - 10:
            events.append(IrrigationEvent(day, depletion, crop.key, stage_name(crop, das)))
            depletion = 0.0
    return events


def gross_m3(net_mm: float, area_ha: float, application_efficiency: float) -> float:
    """Gross water to pump (m3) for a net depth over an area. 1 mm over 1 ha = 10 m3."""
    return net_mm * 10.0 * area_ha / application_efficiency
