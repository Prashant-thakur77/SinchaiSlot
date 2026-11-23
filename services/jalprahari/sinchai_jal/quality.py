"""Water-quality card per borewell.

The starter's TDS/EC probe reports electrical conductivity of the pumped water (ECw). The card applies the
FAO-29 salinity guideline (degree of restriction on use) and the crop salt-tolerance thresholds at 100% yield
potential, so the Saur Mitra can tell a farmer whether this well's water is safe for the crop on the plot.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from sinchai_schemas import constants as C


@dataclass
class QualityCard:
    borewell: str
    ec_dsm: float
    tds_mg_l: float
    restriction: str  # none | slight_moderate | severe
    label_en: str
    label_hi: str
    crops_ok: list[str]
    crops_at_risk: list[str]
    source: str = "SIMULATED probe"

    def to_dict(self) -> dict:
        return asdict(self)


def restriction(ec_dsm: float) -> str:
    if ec_dsm < C.get("water_ec_none_below_dsm"):
        return "none"
    if ec_dsm <= C.get("water_ec_severe_above_dsm"):
        return "slight_moderate"
    return "severe"


_LABEL = {
    "none": ("Safe for all crops here", "सभी फ़सलों के लिए ठीक"),
    "slight_moderate": ("Some salt: watch sensitive crops", "थोड़ा खारा: नाज़ुक फ़सलों पर ध्यान दें"),
    "severe": ("Salty: not for irrigation without leaching", "खारा: बिना धुलाई सिंचाई ठीक नहीं"),
}


def card(borewell: str, ec_dsm: float, source: str = "SIMULATED probe") -> QualityCard:
    if ec_dsm < 0:
        raise ValueError("EC cannot be negative")
    r = restriction(ec_dsm)
    th: dict[str, float] = C.get("crop_ecw_threshold_dsm")
    ok = sorted(k for k, v in th.items() if ec_dsm <= v)
    risk = sorted(k for k, v in th.items() if ec_dsm > v)
    en, hi = _LABEL[r]
    return QualityCard(borewell, round(ec_dsm, 2), round(ec_dsm * C.get("tds_mg_per_l_per_dsm")), r, en, hi, ok, risk,
                       source)
