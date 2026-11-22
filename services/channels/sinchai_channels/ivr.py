"""Missed-call IVR: the farmer rings the pump's number and hangs up (free), the platform calls back.

Flow
  missed_call(caller) -> look up farmer by phone hash -> place callback -> Saathi speaks first (offer)
  -> farmer answers by voice (ASR) or keypad (DTMF 1 = yes, 2 = no) -> Saathi -> TTS -> ...
  -> hang up after a confirmed or declined action, or after 4 turns.

`SimulatedIVR` runs all of this in-process and keeps a transcript. `HttpIVR` is the adapter for a
hosted IVR/telephony provider that posts call events to a webhook (configure IVR_API_URL and
IVR_API_KEY); it is not needed for the demo.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from .base import Transcript, TurnHandler, session_id_for

DTMF = {"1": "1", "2": "2", "9": "help", "0": "operator"}


@dataclass
class CallState:
    transcript: Transcript
    turns: int = 0
    open: bool = True


@dataclass
class SimulatedIVR:
    handler: TurnHandler
    asr: object | None = None  # speech adapter with .transcribe(audio|text, lang) -> text
    tts: object | None = None  # speech adapter with .synthesize(text, lang) -> dict
    calls: dict[str, CallState] = field(default_factory=dict)
    max_turns: int = 6

    def missed_call(self, farmer_id: str) -> dict:
        sid = session_id_for("ivr", farmer_id)
        tr = Transcript(sid, "ivr", farmer_id)
        tr.add("system", "missed call received; calling back (free for the farmer)")
        cs = CallState(tr)
        self.calls[sid] = cs
        out = self.handler(farmer_id, sid, "", True)
        self._say(cs, out)
        return {"session_id": sid, **out, "transcript": tr.turns}

    def farmer_says(self, session_id: str, text: str | None = None, dtmf: str | None = None,
                    language: str = "hi") -> dict:
        cs = self.calls[session_id]
        if not cs.open:
            return {"session_id": session_id, "reply": "", "closed": True, "transcript": cs.transcript.turns}
        heard = DTMF.get(dtmf, dtmf) if dtmf else text or ""
        if text and self.asr is not None:
            heard = self.asr.transcribe(text, language)["text"]
        cs.transcript.add("farmer", heard, dtmf=dtmf)
        out = self.handler(cs.transcript.farmer_id, session_id, heard, False)
        self._say(cs, out)
        cs.turns += 1
        if out.get("pending") is None and any(c.get("confirmed") for c in out.get("tool_calls", [])) \
                or out.get("intent") == "no" or cs.turns >= self.max_turns:
            cs.open = False
            cs.transcript.add("system", "call ended")
        return {"session_id": session_id, **out, "closed": not cs.open, "transcript": cs.transcript.turns}

    def outbound(self, farmer_id: str, text: str, language: str) -> dict:
        """Plan-change callback (no farmer input needed)."""
        sid = session_id_for("ivr-out", farmer_id)
        tr = Transcript(sid, "ivr_callback", farmer_id)
        audio = self.tts.synthesize(text, language) if self.tts else None
        tr.add("saathi", text, audio=audio)
        return {"session_id": sid, "transcript": tr.turns}

    def _say(self, cs: CallState, out: dict) -> None:
        audio = self.tts.synthesize(out.get("reply", ""), out.get("language", "hi")) if self.tts else None
        cs.transcript.add("saathi", out.get("reply", ""), audio=audio, tool_calls=[c["tool"] for c in out.get("tool_calls", [])])


class HttpIVR:
    """Adapter for a hosted telephony provider (webhook-driven). Requires IVR_API_URL and IVR_API_KEY."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url, self.api_key = base_url.rstrip("/"), api_key

    def place_callback(self, to_number: str, webhook_url: str) -> dict:
        r = httpx.post(f"{self.base_url}/calls", headers={"Authorization": f"Bearer {self.api_key}"},
                       json={"to": to_number, "webhook": webhook_url}, timeout=10)
        r.raise_for_status()
        return r.json()
