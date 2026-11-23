"""Offline language understanding for Saathi: intents and slots in Hindi, Maithili, Bhojpuri and
English, Devanagari or romanised. Deterministic, so it runs with no network and is fully testable.

Maithili and Bhojpuri word lists were drafted for the prototype and must be reviewed by native
speakers before field use (docs/decisions/0005-languages.md).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

INTENTS: dict[str, list[str]] = {
    "yes": ["हाँ", "हां", "हाँ जी", "जी हाँ", "जी", "हँ", "हं", "ठीक", "ठीक है", "ठीक अछि", "बेस", "करू", "कर दीं", "कर दो",
            "haan", "han", "ha", "haa", "ji", "theek", "thik", "yes", "ok", "okay", "sure", "confirm", "1"],
    "no": ["नहीं", "नही", "ना", "नै", "नइ", "मत", "nahi", "nahin", "na", "nai", "no", "dont", "don't", "2"],
    "cancel": ["रद्द", "कैंसल", "कैन्सल", "नहीं चाहिए", "नै चाही", "ना चाहीं", "बुकिंग हटा", "cancel", "radd"],
    "price": ["कितना", "कितने", "कतेक", "केतना", "दाम", "रेट", "भाव", "पैसा लगेगा", "खर्च", "price", "rate",
              "cost", "kitna", "katek", "ketna", "daam"],
    "when": ["कब", "कहिया", "कखन", "कब मिलेगा", "समय", "टाइम", "kab", "kahiya", "kakhan", "when", "time", "slot"],
    "book": ["पानी चाहिए", "पानी चाही", "पानी चाहीं", "पानी दे", "पानी दिअ", "पानी द", "पानि", "पटवन", "सिंचाई",
             "पटाना", "पानी लेना", "पानी लगाना", "बुक", "बुकिंग", "book", "booking", "irrigat", "pani chahiye",
             "pani chahi", "patwan", "sinchai", "sinchaai", "paani", "pani", "water"],
    "balance": ["बाकी", "बकाया", "हिसाब", "बैलेंस", "कितना देना", "balance", "due", "owe", "baki", "baaki",
                "bakaya", "hisab", "hisaab"],
    "pay": ["पेमेंट", "भुगतान", "यूपीआई", "upi", "pay", "payment", "bhugtan"],
    "schemes": ["योजना", "सब्सिडी", "अनुदान", "कुसुम", "scheme", "subsidy", "yojana", "anudan", "kusum"],
    "issue": ["खराब", "नहीं आ रहा", "नै आबि रहल", "बंद है", "बंद", "शिकायत", "दिक्कत", "समस्या", "लीक", "problem",
              "complaint", "kharab", "band", "leak", "not working"],
    "why": ["क्यों", "किएक", "काहे", "बदल", "why", "kyon", "kyu", "kahe", "changed", "badal"],
    "status": ["मेरी बुकिंग", "हमार बुकिंग", "हमर बुकिंग", "स्टेटस", "status", "my booking", "meri booking"],
    "diesel": ["डीजल", "diesel", "दूसरा पंप", "other pump"],
    "greet": ["नमस्ते", "नमस्कार", "प्रणाम", "राम राम", "hello", "hi", "namaste", "pranam"],
    "help": ["मदद", "सहायता", "help", "madad"],
    "harvest": ["फसल के बाद", "फ़सल के बाद", "फसल बाद", "कटनी के बाद", "कटनी बाद", "बाद में देंगे", "बाद में दूँगा",
                "बाद मे देब", "बाद में देब", "बाद में दीहल", "उधार", "after harvest", "pay later", "later pay",
                "fasal ke baad", "baad mein denge", "udhar", "udhaar"],
    "advice": ["कीड़ा", "कीड़े", "कीड़ों", "कीट", "रोग", "बीमारी", "खाद", "यूरिया", "डीएपी", "बीज", "किस्म", "दवा",
               "दवाई", "रतुआ", "मंडी", "पिल्लू", "pest", "insect", "disease", "fertiliser", "fertilizer", "urea",
               "seed", "variety", "mandi", "keeda", "khad", "beej", "dawai"],
}
# Higher wins when several intents match.
PRIORITY = ["cancel", "harvest", "advice", "issue", "why", "schemes", "balance", "pay", "status", "diesel", "price", "when", "book",
            "no", "yes", "help", "greet"]

LANG_MARKERS = {
    "mai": ["अछि", "छी", "छै", "चाही", "कहिया", "किएक", "कतेक", "नै", "हँ", "दिअ", "हमर", "अहाँ", "कखन", "सकैत",
            "achhi", "chhi", "katek", "kiek", "ahan", "hamar"],
    "bho": ["बा", "बानी", "चाहीं", "केतना", "काहे", "हमार", "रउआ", "रउरा", "बाटे", "कइसे", "ketna", "kahe", "rauwa",
            "bani"],
    "hi": ["है", "हैं", "चाहिए", "कितना", "क्यों", "मेरा", "मेरी", "आप", "कब", "chahiye", "kitna", "kyon", "mera",
           "aap"],
}

INJECTION = re.compile(r"(ignore (all|previous|the above)|system prompt|you are now|disregard|act as|"
                       r"developer mode|<\s*/?\s*(system|tool)|\bBEGIN\b.*\bINSTRUCTIONS\b)", re.I)


@dataclass
class Parsed:
    intent: str
    language: str
    m3: float | None = None
    hours: float | None = None
    booking_id: str | None = None
    all_intents: list[str] = field(default_factory=list)
    injection_flag: bool = False
    text: str = ""


def clean(text: str, limit: int = 500) -> str:
    t = unicodedata.normalize("NFC", text)
    t = "".join(ch for ch in t if unicodedata.category(ch)[0] != "C" or ch in "\n ")
    return t.strip()[:limit]


DEVA = "\u0900-\u097F"


def _has(text_l: str, kw: str) -> bool:
    """Keyword match with word boundaries. Short keywords need both boundaries (so "ना" does not match
    inside "देना"); longer ones only a left boundary, so inflected forms ("पटवनक", "booking") match."""
    kw_l = kw.lower()
    if kw_l.isascii():
        right = "(?![a-z])" if len(kw_l) <= 3 else ""
        return re.search(rf"(?<![a-z0-9]){re.escape(kw_l)}{right}", text_l) is not None
    right = f"(?![{DEVA}])" if len(kw_l) <= 3 else ""
    return re.search(rf"(?<![{DEVA}]){re.escape(kw_l)}{right}", text_l) is not None


def detect_language(text: str, default: str = "hi") -> str:
    tl = text.lower()
    scores = {lang: sum(1 for m in marks if _has(tl, m)) for lang, marks in LANG_MARKERS.items()}
    best = max(scores, key=lambda k: scores[k])
    if scores[best] > 0 and (scores[best] > scores.get("hi", 0) or best == "hi"):
        return best
    if all(ord(c) < 128 for c in text) and re.search(r"[a-z]", tl):
        hinglish = sum(1 for w in ("hai", "chahiye", "kitna", "kab", "paani", "pani", "haan", "nahi", "mera", "kal")
                       if _has(tl, w))
        return "hi" if hinglish else "en"
    return default


DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def parse(text: str, default_lang: str = "hi") -> Parsed:
    t = clean(text)
    tl = t.lower().translate(DEVANAGARI_DIGITS)
    found = [i for i in PRIORITY if any(_has(tl, kw) for kw in INTENTS[i])]
    intent = found[0] if found else ("yes" if tl in ("1",) else "unknown")
    # A bare yes/no outranks weaker cues ("हाँ बुक करो" is a yes to a pending offer).
    if "yes" in found and any(_has(tl, k) for k in ("हाँ", "हां", "haan", "yes", "हँ", "ji", "जी")) and \
            not {"cancel", "issue", "why", "price", "balance"} & set(found):
        intent = "yes"
    if "no" in found and intent in ("book", "when") and any(_has(tl, k) for k in ("नहीं", "nahi", "no", "नै", "ना")):
        intent = "no"
    m3 = None
    hours = None
    mm = re.search(r"(\d+(?:\.\d+)?)\s*(m3|m³|घन\s*मीटर|cubic|क्यूबिक|kyubik)", tl)
    if mm:
        m3 = float(mm.group(1))
    mh = re.search(r"(\d+(?:\.\d+)?)\s*(घंटा|घंटे|घंटा|ghanta|ghante|hour|hours|hr)", tl)
    if mh:
        hours = float(mh.group(1))
    mb = re.search(r"\b(b\d{7})\b", tl)
    return Parsed(intent=intent, language=detect_language(t, default_lang), m3=m3, hours=hours,
                  booking_id=mb.group(1).upper() if mb else None, all_intents=found,
                  injection_flag=bool(INJECTION.search(t)), text=t)
