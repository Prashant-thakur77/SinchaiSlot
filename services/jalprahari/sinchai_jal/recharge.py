"""Recharge pairing: suggest structures that put back what a pump cluster takes out.

Extraction comes from the Rasid ledger (drive-metered m3). Offset options are a farm pond (seepage of its fills
over the monsoon) and a CGWB-style recharge shaft. The output is counts, cost and cost per m3 recharged per
year, so a funder can pair a recharge grant with the pump it offsets. Every parameter is in constants.yaml
with its kind (published or assumption).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from sinchai_schemas import constants as C


@dataclass
class RechargeOption:
    kind: str
    name_en: str
    name_hi: str
    m3_per_year_each: float
    cost_rs_each: float
    count: int
    total_m3_per_year: float
    total_cost_rs: float
    rs_per_m3_year: float  # capex per m3 of annual recharge
    source_kind: str

    def to_dict(self) -> dict:
        return asdict(self)


def pond_m3_per_year() -> float:
    return C.get("farm_pond_m3") * C.get("farm_pond_fills_per_monsoon") * C.get("farm_pond_seepage_share")


def pair(extraction_m3_per_year: float, offset_share: float = 1.0) -> dict:
    """Structures needed to recharge `offset_share` of the cluster's annual extraction."""
    if extraction_m3_per_year < 0 or not 0 < offset_share <= 2:
        raise ValueError("bad extraction or offset share")
    target = extraction_m3_per_year * offset_share
    opts = []
    for kind, en, hi, each, cost, sk in (
        ("farm_pond", "Farm pond (30 x 20 x 2 m)", "खेत तालाब", pond_m3_per_year(), C.get("farm_pond_cost_rs"),
         "assumption"),
        ("recharge_shaft", "Recharge shaft", "रिचार्ज शाफ़्ट", C.get("recharge_shaft_m3_per_year"),
         C.get("recharge_shaft_cost_rs"), "published (CGWB planning norm, not Bihar)"),
    ):
        n = max(1, math.ceil(target / each)) if target > 0 else 0
        opts.append(RechargeOption(kind, en, hi, round(each), cost, n, round(n * each), n * cost,
                                   round(cost / each, 1), sk))
    best = min(opts, key=lambda o: (o.total_cost_rs, -o.total_m3_per_year)) if target > 0 else None
    return {"extraction_m3_per_year": round(extraction_m3_per_year), "target_m3_per_year": round(target),
            "options": [o.to_dict() for o in opts], "cheapest": best.kind if best else None}
