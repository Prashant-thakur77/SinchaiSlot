"""Jal Prahari: the cluster groundwater budget.

The budget is a hard cap on what the shared pump extracts in a year and in each season. It is
derived from an annual extraction depth over the command area (constants: seasonal_budget_mm)
scaled by the block's CGWB category. Seasons get shares in proportion to their FAO-56 demand, so
the rabi wheat irrigations are not eaten by summer vegetables.

The engine is deterministic. Agents only explain it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sinchai_schemas import constants as C

# Scaling of the cap by CGWB block category. Modelling assumption, documented in
# docs/decisions/0003: a Safe block keeps the full cap, each category step cuts it.
CATEGORY_FACTOR = {"Safe": 1.0, "Semi-critical": 0.8, "Critical": 0.6, "Over-exploited": 0.4}
SEASON_SHARE = {"rabi": 0.35, "zaid": 0.40, "kharif": 0.25}
ALERT_FRACTION = 0.8


def season_of(d: date) -> str:
    if d.month in (11, 12, 1, 2):
        return "rabi"
    if d.month in (3, 4, 5, 6):
        return "zaid"
    return "kharif"


@dataclass
class Alert:
    day: date
    scope: str
    used_fraction: float
    message_en: str
    message_hi: str


@dataclass
class WaterBudget:
    annual_m3: float
    season_shares: dict[str, float] = field(default_factory=lambda: dict(SEASON_SHARE))
    used_m3: dict[str, float] = field(default_factory=lambda: {s: 0.0 for s in SEASON_SHARE})
    alerts: list[Alert] = field(default_factory=list)
    _alerted: set[str] = field(default_factory=set)
    days_bound: int = 0

    @classmethod
    def for_cluster(cls, command_area_ha: float | None = None, category: str | None = None,
                    depth_mm: float | None = None) -> WaterBudget:
        area = command_area_ha if command_area_ha is not None else C.get("command_area_acres") * 0.404686
        depth = depth_mm if depth_mm is not None else C.get("seasonal_budget_mm")
        cat = category or C.get("samastipur_block_category")
        return cls(annual_m3=depth * area * 10.0 * CATEGORY_FACTOR[cat])

    def season_cap(self, season: str) -> float:
        return self.annual_m3 * self.season_shares[season]

    def remaining(self, d: date) -> float:
        s = season_of(d)
        season_left = self.season_cap(s) - self.used_m3[s]
        annual_left = self.annual_m3 - sum(self.used_m3.values())
        return max(min(season_left, annual_left), 0.0)

    def record(self, d: date, m3: float) -> None:
        if m3 < 0:
            raise ValueError("negative extraction")
        s = season_of(d)
        if m3 > self.remaining(d) + 1e-6:
            raise ValueError(f"extraction {m3:.1f} m3 exceeds remaining budget {self.remaining(d):.1f} m3")
        self.used_m3[s] += m3
        frac = self.used_m3[s] / self.season_cap(s)
        key = f"{d.year}-{s}"
        if frac >= ALERT_FRACTION and key not in self._alerted:
            self._alerted.add(key)
            self.alerts.append(Alert(d, s, frac,
                                     f"{s} groundwater budget {frac:.0%} used",
                                     f"{s} मौसम का भूजल बजट {frac:.0%} इस्तेमाल हो चुका है"))

    def mark_bound(self) -> None:
        self.days_bound += 1

    def reset_year(self) -> None:
        self.used_m3 = {s: 0.0 for s in self.season_shares}


@dataclass(frozen=True)
class DryRunGuard:
    """Edge-side dry-run cut-off.

    Trip when the pump runs above cut-off speed but draws less than `underload_fraction` of the power
    expected at that speed for `persist_s` seconds. This mirrors the drive's own process-underload
    function (ULF, Altivar Solar user manual PKR47019 p.119-120), duplicated at the edge so the
    cut-off works even when the drive parameter is not configured.
    """

    underload_fraction: float = 0.6
    persist_s: float = 20.0

    def underloaded(self, expected_kw: float, measured_kw: float) -> bool:
        return expected_kw > 0.3 and measured_kw < self.underload_fraction * expected_kw


def awd_irrigate(field_water_level_mm: float, stage: str, threshold_mm: float = -150.0) -> bool:
    """Alternate wetting and drying: irrigate when perched water drops below the threshold.

    Keep the field flooded in the initial (establishment) and flowering stages.
    """
    if stage in ("initial", "flowering"):
        return field_water_level_mm < 0
    return field_water_level_mm < threshold_mm
