"""Soil parameters from a Soil Health Card.

The card gives pH, EC, organic carbon and nutrients; some state cards also print the texture class. The
planner needs total available water (TAW) per metre of root zone, which follows from texture (FAO-56 table 19,
mid-point of theta_FC - theta_WP). Nutrient ratings are shown to the farmer, and fertiliser advice is handed to
Bharat-VISTAAR: SinchaiSlot sizes water, it does not prescribe fertiliser.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .fao56 import CROPS, TAW_MM_PER_M

# FAO-56 table 19: (theta_FC - theta_WP) range in m3/m3 by texture; TAW mm/m = 1000 x mid-point.
TEXTURE_TAW_RANGE = {
    "sand": (0.05, 0.11), "loamy sand": (0.06, 0.12), "sandy loam": (0.11, 0.15), "loam": (0.13, 0.18),
    "silt loam": (0.13, 0.19), "silt": (0.15, 0.21), "silty clay loam": (0.13, 0.18), "silty clay": (0.13, 0.19),
    "clay": (0.12, 0.20), "clay loam": (0.13, 0.18), "sandy clay loam": (0.11, 0.15),
}
TEXTURE_HI = {"sand": "बलुई", "loamy sand": "दोमट बलुई", "sandy loam": "बलुई दोमट", "loam": "दोमट", "silt loam": "गाद दोमट",
              "silt": "गाद", "silty clay loam": "गाद चिकनी दोमट", "silty clay": "गाद चिकनी", "clay": "चिकनी",
              "clay loam": "चिकनी दोमट", "sandy clay loam": "बलुई चिकनी दोमट"}

# Soil-test ratings commonly printed on Indian Soil Health Cards (low / medium / high bounds).
# kind: assumption - confirm against the issuing state laboratory's card.
RATINGS = {
    "oc_pct": (0.5, 0.75), "n_kg_ha": (280, 560), "p_kg_ha": (10, 25), "k_kg_ha": (108, 280),
}


@dataclass
class SoilCard:
    texture: str | None = None
    ph: float | None = None
    ec_dsm: float | None = None
    oc_pct: float | None = None
    n_kg_ha: float | None = None
    p_kg_ha: float | None = None
    k_kg_ha: float | None = None
    s_ppm: float | None = None
    zn_ppm: float | None = None
    card_no: str | None = None


def taw_mm_per_m(texture: str | None) -> tuple[float, str]:
    if texture:
        t = texture.strip().lower()
        if t in TEXTURE_TAW_RANGE:
            lo, hi = TEXTURE_TAW_RANGE[t]
            return round((lo + hi) / 2 * 1000, 0), f"FAO-56 table 19, {t}"
    return TAW_MM_PER_M, "default loam (texture not on the card)"


def rate(key: str, v: float | None) -> str | None:
    if v is None or key not in RATINGS:
        return None
    lo, hi = RATINGS[key]
    return "low" if v < lo else "medium" if v <= hi else "high"


def ph_class(ph: float | None) -> str | None:
    if ph is None:
        return None
    return "acidic" if ph < 6.5 else "neutral" if ph <= 7.5 else "alkaline" if ph <= 8.5 else "strongly alkaline"


def apply(card: SoilCard, crop_key: str = "wheat") -> dict:
    """What the card changes for the planner and what the farmer sees."""
    taw, basis = taw_mm_per_m(card.texture)
    crop = CROPS[crop_key]
    raw_mm = crop.p_depletion * taw * crop.root_depth_m
    default_raw = crop.p_depletion * TAW_MM_PER_M * crop.root_depth_m
    flags = []
    if card.ph is not None and card.ph > 8.5:
        flags.append({"en": "Strongly alkaline soil: ask about gypsum", "hi": "मिट्टी बहुत क्षारीय: जिप्सम के बारे में पूछें"})
    if card.ec_dsm is not None and card.ec_dsm > 1.0:
        flags.append({"en": "Salty soil: water a little extra to leach salt", "hi": "मिट्टी में नमक: नमक धोने को थोड़ा ज़्यादा पानी"})
    return {
        "card": asdict(card), "taw_mm_per_m": taw, "taw_basis": basis,
        "texture_hi": TEXTURE_HI.get((card.texture or "").lower()),
        "crop": crop_key, "irrigate_when_depleted_mm": round(raw_mm), "default_irrigate_when_depleted_mm": round(default_raw),
        "interval_change": round(raw_mm / default_raw - 1, 3),
        "ratings": {k: rate(k, getattr(card, k)) for k in RATINGS}, "ph_class": ph_class(card.ph), "flags": flags,
        "advice_handoff": "Fertiliser advice: Bharat-VISTAAR (SinchaiSlot sizes water only)",
    }
