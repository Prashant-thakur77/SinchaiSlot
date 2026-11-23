"""Bharat-VISTAAR handoff for agronomy questions.

SinchaiSlot answers water, slots and money. When a farmer asks about pests, seed, fertiliser or prices,
Saathi does not improvise agronomy: it packs the question with the context it already holds (crop, stage,
district, soil card, language) and hands it to Bharat-VISTAAR, the national advisory service (helpline
155261), then tells the farmer how the advice will reach them.

`SimulatedVistaar` records the handoff and returns a reference. `HttpVistaar` posts the same packet to an
integration endpoint (VISTAAR_URL, VISTAAR_TOKEN). No public API was found for it: this adapter is UNVERIFIED and
is shaped as a plain JSON POST to be adapted to whatever integration the programme offers.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime

import httpx

HELPLINE = "155261"

TOPICS = {
    "pest": ("pest or disease", "कीट या रोग"),
    "fertiliser": ("fertiliser and soil nutrients", "खाद और पोषक तत्व"),
    "seed": ("seed and variety", "बीज और किस्म"),
    "price": ("mandi price", "मंडी भाव"),
    "weather": ("weather advisory", "मौसम सलाह"),
    "other": ("farm advice", "खेती की सलाह"),
}


@dataclass
class Handoff:
    question: str
    topic: str
    language: str
    farmer_ref: str  # pseudonymous id, never a phone number
    crop: str | None = None
    stage: str | None = None
    district: str = "Samastipur"
    soil: dict | None = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat(timespec="seconds"))

    def reference(self) -> str:
        return "VST-" + hashlib.sha256(f"{self.farmer_ref}|{self.question}|{self.created_at}".encode()).hexdigest()[:8].upper()


class SimulatedVistaar:
    name = "simulated"

    def __init__(self) -> None:
        self.sent: list[dict] = []

    def handoff(self, h: Handoff) -> dict:
        rec = {**asdict(h), "reference": h.reference(), "status": "queued", "channel": "callback from advisory line",
               "helpline": HELPLINE, "label": "SIMULATED handoff"}
        self.sent.append(rec)
        return rec


class HttpVistaar:
    name = "http"

    def __init__(self, url: str, token: str | None = None) -> None:
        self.url, self.token = url, token

    def handoff(self, h: Handoff) -> dict:
        r = httpx.post(self.url, json={**asdict(h), "reference": h.reference()}, timeout=10,
                       headers={"Authorization": f"Bearer {self.token}"} if self.token else {})
        r.raise_for_status()
        return {**r.json(), "reference": h.reference(), "helpline": HELPLINE}


def classify(text: str) -> str:
    t = text.lower()
    rules = [("pest", ("कीड़", "कीट", "रोग", "बीमारी", "pest", "insect", "disease", "fungus", "रतुआ", "पिल्लू")),
             ("fertiliser", ("खाद", "यूरिया", "डीएपी", "fertili", "urea", "dap", "potash", "पोटाश")),
             ("seed", ("बीज", "किस्म", "seed", "variety")),
             ("price", ("भाव", "मंडी", "दाम", "price", "mandi", "rate")),
             ("weather", ("मौसम", "बारिश", "weather", "rain"))]
    for topic, keys in rules:
        if any(k in t for k in keys):
            return topic
    return "other"


_ADAPTER = None


def adapter():
    global _ADAPTER
    if _ADAPTER is None:
        url = os.getenv("VISTAAR_URL")
        _ADAPTER = HttpVistaar(url, os.getenv("VISTAAR_TOKEN")) if url else SimulatedVistaar()
    return _ADAPTER
