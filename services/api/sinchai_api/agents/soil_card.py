"""Read a Soil Health Card photo into structured soil values.

Providers:
  hosted  - a vision-capable hosted LLM (LLM_PROVIDER=anthropic) returns the card's fields as JSON under a
            fixed schema; values the model cannot read come back null, never guessed.
  sample  - offline simulator: recognises the bundled sample card (by hash) and returns its printed values.
            Any other photo offline returns needs_manual_entry, and the Saur Mitra types the values in.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import fields
from pathlib import Path

from sinchai_planner.soil import SoilCard

from ..settings import settings
from .runtime import anthropic_available

ASSETS = Path(__file__).resolve().parents[1] / "assets"
SAMPLE = ASSETS / "soil_card_sample.png"
SAMPLE_VALUES = ASSETS / "soil_card_sample.json"

_NUM = {"type": ["number", "null"]}
SCHEMA = {
    "type": "object",
    "properties": {
        "card_no": {"type": ["string", "null"]}, "texture": {"type": ["string", "null"]},
        "ph": _NUM, "ec_dsm": _NUM, "oc_pct": _NUM, "n_kg_ha": _NUM, "p_kg_ha": _NUM, "k_kg_ha": _NUM,
        "s_ppm": _NUM, "zn_ppm": _NUM,
    },
    "required": ["card_no", "texture", "ph", "ec_dsm", "oc_pct", "n_kg_ha", "p_kg_ha", "k_kg_ha", "s_ppm", "zn_ppm"],
    "additionalProperties": False,
}

PROMPT = (
    "This is a photo of an Indian Soil Health Card. Read only values printed on the card. Units: EC in dS/m, "
    "organic carbon in %, available N, P, K in kg/ha, S and Zn in ppm. Texture is the printed texture class in "
    "English (for example 'loam', 'sandy loam', 'clay'), translated from Hindi if needed. Use null for anything "
    "not printed or not legible. Do not estimate."
)


def _card_from(d: dict) -> SoilCard:
    names = {f.name for f in fields(SoilCard)}
    return SoilCard(**{k: v for k, v in d.items() if k in names})


def read(image: bytes, media_type: str = "image/png") -> dict:
    digest = hashlib.sha256(image).hexdigest()
    if SAMPLE.exists() and digest == hashlib.sha256(SAMPLE.read_bytes()).hexdigest():
        vals = json.loads(SAMPLE_VALUES.read_text())
        return {"provider": "sample", "label": "SIMULATED reader (bundled sample card)", "card": vals}
    if anthropic_available():
        import anthropic

        client = anthropic.Anthropic()
        r = client.messages.create(
            model=settings().anthropic_model, max_tokens=2000,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                             "data": base64.standard_b64encode(image).decode()}},
                {"type": "text", "text": PROMPT}]}],
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        )
        text = next(b.text for b in r.content if b.type == "text")
        return {"provider": "hosted", "label": "Read by hosted vision model; check against the card", "card": json.loads(text)}
    return {"provider": "none", "needs_manual_entry": True,
            "label": "No hosted reader configured: type the values from the card", "card": None}


def to_card(d: dict) -> SoilCard:
    return _card_from(d)
