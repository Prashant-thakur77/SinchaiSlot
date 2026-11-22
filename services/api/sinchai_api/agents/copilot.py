"""Saur Mitra Copilot: guided, step-by-step fault diagnosis.

Steps come from the Altivar Solar ATV320 manual's documented causes and remedies for each fault
(docs/schneider/fault_codes.yaml, with page references), preceded by field checks that ask the
Saur Mitra for an observation. Field checks are marked `source: field practice` so they are never
mistaken for manual text. With no fault code, the symptom text is matched to faults by TF-IDF
retrieval over the fault table.
"""

from __future__ import annotations

from functools import lru_cache

from sinchai_devices import altivar_map as M
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Field checks that come before the manual's remedies (observations the agent asks for).
FIELD_CHECKS: dict[str, list[dict]] = {
    "ULF": [
        {"en": "Look at the delivery pipe outlet. Is water coming out?", "hi": "डिलीवरी पाइप का मुँह देखें। पानी आ रहा है?",
         "ask": "water_flowing"},
        {"en": "Check the borewell level with the dip tape, or listen at the pump head for air gurgling.",
         "hi": "डिप टेप से बोरवेल का पानी स्तर देखें, या पंप के पास हवा की गुड़गुड़ सुनें।", "ask": "water_level_m"},
        {"en": "If the well is low, wait 30 minutes for recovery before resetting. Do not reset repeatedly.",
         "hi": "पानी कम है तो रीसेट से पहले 30 मिनट रुकें। बार-बार रीसेट न करें।", "ask": None},
    ],
    "OHF": [
        {"en": "Touch-test is unsafe; look instead: is the drive enclosure in direct sun or are the vents blocked by dust?",
         "hi": "छूकर न देखें। देखें: ड्राइव बॉक्स सीधी धूप में है या जाली धूल से बंद है?", "ask": "vents_blocked"},
        {"en": "Clean the vents with a dry brush with the drive isolated, and shade the enclosure.",
         "hi": "ड्राइव बंद करके सूखे ब्रश से जाली साफ़ करें और बॉक्स पर छाया करें।", "ask": None},
    ],
    "OLF": [
        {"en": "Is the pump making grinding noise or is sand coming with the water?",
         "hi": "क्या पंप से घिसने की आवाज़ है या पानी के साथ बालू आ रहा है?", "ask": "noise_or_sand"},
    ],
    "USF": [
        {"en": "Look at the solar panels: shade, heavy dust or a loose connector at the junction box?",
         "hi": "सोलर पैनल देखें: छाया, बहुत धूल, या जंक्शन बॉक्स पर ढीला कनेक्टर?", "ask": "panels_ok"},
    ],
    "OPF1": [
        {"en": "Check the three motor cable joints at the well head for a burnt or loose joint (power off first).",
         "hi": "बिजली बंद करके बोरवेल पर मोटर केबल के तीनों जोड़ देखें, कोई जला या ढीला तो नहीं।", "ask": "joint_ok"},
    ],
    "SLF1": [
        {"en": "Check the RS-485 cable between the edge controller and the drive's Modbus port.",
         "hi": "एज कंट्रोलर और ड्राइव के मॉडबस पोर्ट के बीच RS-485 केबल देखें।", "ask": "cable_ok"},
    ],
}


@lru_cache(maxsize=1)
def _index():
    fl = list(M.faults().values())
    docs = [f"{f.mnemonic} {f.name} {f.description} {' '.join(f.causes)} {' '.join(f.remedies)}" for f in fl]
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1).fit(docs)
    return fl, vec, vec.transform(docs)


SYMPTOM_HINTS = {
    "dry": "underload no water dry run", "सूख": "underload no water dry run", "पानी नहीं": "underload no water dry run",
    "garam": "overheating drive thermal", "गरम": "overheating drive thermal", "hot": "overheating drive thermal",
    "cloud": "undervoltage supply low", "बादल": "undervoltage supply low", "dhoop": "undervoltage supply low",
    "noise": "motor overload mechanical", "आवाज": "motor overload mechanical", "cable": "output phase loss motor cable",
}


def retrieve(symptoms: str, k: int = 3) -> list[dict]:
    fl, vec, mat = _index()
    q = symptoms + " " + " ".join(v for key, v in SYMPTOM_HINTS.items() if key in symptoms.lower())
    sims = cosine_similarity(vec.transform([q]), mat)[0]
    order = sims.argsort()[::-1][:k]
    return [{"fault": fl[i].mnemonic, "name": fl[i].name, "score": round(float(sims[i]), 3)} for i in order if sims[i] > 0]


def steps_for(code: str) -> list[dict]:
    f = M.faults().get(code)
    if f is None:
        return []
    steps = [{**s, "source": "field practice"} for s in FIELD_CHECKS.get(code, [])]
    for r in f.remedies:
        steps.append({"en": r, "hi": None, "ask": None, "source": "Altivar Solar ATV320 user manual (PKR47019)"})
    steps.append({"en": f"Clearing: {f.clearing}", "hi": None, "ask": None, "source": "manual"})
    return steps


def diagnose_step(code: str | None, step: int = 0, observation: str = "", symptoms: str = "") -> dict:
    if not code:
        cands = retrieve(symptoms or "pump not running")
        return {"fault": None, "candidates": cands,
                "instruction_en": "No fault on the drive. Which of these matches what you see?",
                "instruction_hi": "ड्राइव पर कोई फ़ॉल्ट नहीं है। इनमें से कौन सा आपकी समस्या से मिलता है?", "done": False}
    f = M.faults().get(code)
    if f is None:
        return {"fault": code, "error": "unknown fault code", "done": True}
    steps = steps_for(code)
    # Early exit: water flowing again during a dry-run check means the well recovered.
    if code == "ULF" and step == 1 and observation.strip().lower() in ("yes", "haan", "हाँ", "true"):
        return {"fault": code, "name": f.name, "step": step, "done": True,
                "instruction_en": "Water is back: the well has recovered. Reset the fault and resume the slot.",
                "instruction_hi": "पानी वापस आ गया, कुआँ भर गया। फ़ॉल्ट रीसेट करें और स्लॉट फिर चलाएँ।",
                "next_tool": "reset_fault"}
    i = min(step, len(steps) - 1)
    s = steps[i]
    return {
        "fault": code, "name": f.name, "description": f.description, "causes": list(f.causes),
        "step": i, "of": len(steps), "instruction_en": s["en"], "instruction_hi": s["hi"], "ask": s["ask"],
        "source": s["source"], "done": i == len(steps) - 1,
        "next_tool": "reset_fault" if i == len(steps) - 1 else None, "verified": f.verified,
    }
