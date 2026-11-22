"""Prayogshala synthetic village: households, plots, crops and the FAO-56 demand trace.

All plots share one weather series (real NASA POWER), so every policy sees the identical list of
irrigation requests: the "same demand trace" required by PLAN.md 7.2. Labelled SIMULATED.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sinchai_planner import fao56
from sinchai_schemas import constants as C


@dataclass
class Household:
    id: str
    tenant: bool
    owner: bool
    language: str
    plots: list[str] = field(default_factory=list)


@dataclass
class Plot:
    id: str
    household: str
    area_ha: float
    crops: dict[int, dict[str, str]] = field(default_factory=dict)  # year -> season -> crop key
    lon: float = 0.0
    lat: float = 0.0


@dataclass
class IrrRequest:
    id: str
    plot: str
    household: str
    tenant: bool
    owner: bool
    crop: str
    stage: str
    day: date
    deadline: date
    net_mm: float
    gross_m3: float


@dataclass
class Village:
    households: list[Household]
    plots: list[Plot]
    seed: int

    @property
    def area_ha(self) -> float:
        return sum(p.area_ha for p in self.plots)

    def household(self, hid: str) -> Household:
        return next(h for h in self.households if h.id == hid)


def _pick(rng: np.random.Generator, mix: dict[str, float]) -> str:
    keys = list(mix)
    return str(rng.choice(keys, p=np.array([mix[k] for k in keys]) / sum(mix.values())))


def make_village(seed: int, n_households: int | None = None, years: tuple[int, ...] = (2023, 2024, 2025)) -> Village:
    rng = np.random.default_rng(seed)
    n = n_households or int(C.get("households_per_pump"))
    command_ha = C.get("command_area_acres") * 0.404686
    owner_ha = C.get("owner_plot_ha")
    tenant_share = C.get("tenant_share")
    langs = ["mai", "hi", "bho", "hi", "mai"]

    households: list[Household] = [Household("H00", tenant=False, owner=True, language="mai")]
    for i in range(1, n):
        households.append(Household(f"H{i:02d}", tenant=bool(rng.random() < tenant_share), owner=False,
                                    language=langs[i % len(langs)]))
    # Non-owner holdings: lognormal around the Bihar average, rescaled to fill the command area.
    raw = rng.lognormal(mean=np.log(C.get("bihar_avg_holding_ha")), sigma=0.6, size=n - 1)
    raw = raw / raw.sum() * (command_ha - owner_ha)
    plots: list[Plot] = []
    cx, cy = C.get("site_lon"), C.get("site_lat")
    areas = [owner_ha, *raw.tolist()]
    for i, h in enumerate(households):
        # Owner's land in two plots, others one plot each.
        parts = [areas[i] * 0.6, areas[i] * 0.4] if h.owner else [areas[i]]
        for j, a in enumerate(parts):
            pid = f"{h.id}P{j}"
            ang = rng.uniform(0, 2 * np.pi)
            r = 0.002 + 0.0035 * np.sqrt(rng.random())
            p = Plot(pid, h.id, float(a), lon=cx + r * np.cos(ang), lat=cy + r * np.sin(ang) * 0.9)
            for y in years:
                p.crops[y] = {
                    "rabi": _pick(rng, C.get("crop_mix_rabi")),
                    "zaid": _pick(rng, C.get("crop_mix_zaid")),
                    "kharif": _pick(rng, C.get("crop_mix_kharif")),
                }
            plots.append(p)
            h.plots.append(pid)
    return Village(households, plots, seed)


def demand_trace(village: Village, daily: pd.DataFrame, start: date, end: date,
                 awd: bool = False, sow_jitter_sd_days: float = 5.0) -> list[IrrRequest]:
    """FAO-56 irrigation requests for every plot whose need falls in [start, end]."""
    rng = np.random.default_rng(village.seed + 7919)
    eff = C.get("application_efficiency")
    window = int(C.get("request_window_days"))
    hh = {h.id: h for h in village.households}
    out: list[IrrRequest] = []
    k = 0
    for p in village.plots:
        for y, seasons in sorted(p.crops.items()):
            for _season, crop_key in seasons.items():
                if crop_key == "fallow":
                    continue
                base = fao56.CROPS[crop_key]
                jitter = int(round(rng.normal(0, sow_jitter_sd_days)))
                sow = base.sowing_date(y) + timedelta(days=jitter)
                crop = fao56.Crop(**{**base.__dict__, "sow_month": sow.month, "sow_day": sow.day})
                for ev in fao56.simulate_plot(crop, daily, sow.year, awd=awd and crop.is_paddy):
                    if not (start <= ev.day <= end):
                        continue
                    k += 1
                    h = hh[p.household]
                    dl = window - 1 if crop.is_paddy else window
                    out.append(IrrRequest(
                        id=f"Q{village.seed}-{k:05d}", plot=p.id, household=h.id, tenant=h.tenant, owner=h.owner,
                        crop=crop_key, stage=ev.stage, day=ev.day, deadline=ev.day + timedelta(days=dl),
                        net_mm=ev.net_mm, gross_m3=fao56.gross_m3(ev.net_mm, p.area_ha, eff),
                    ))
    out.sort(key=lambda r: (r.day, r.id))
    return out
