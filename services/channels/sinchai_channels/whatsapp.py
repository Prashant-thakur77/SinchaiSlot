"""WhatsApp: text and voice notes.

`SimulatedWhatsApp` keeps an in-process chat per farmer; voice notes go through the ASR adapter.
`WhatsAppCloud` sends replies through the WhatsApp Cloud API (configure WHATSAPP_TOKEN and
WHATSAPP_PHONE_ID); inbound messages arrive on the platform's /channels/whatsapp/webhook route.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from .base import Transcript, TurnHandler, session_id_for


@dataclass
class SimulatedWhatsApp:
    handler: TurnHandler
    asr: object | None = None
    chats: dict[str, Transcript] = field(default_factory=dict)

    def _chat(self, farmer_id: str) -> Transcript:
        if farmer_id not in self.chats:
            self.chats[farmer_id] = Transcript(session_id_for("wa", farmer_id), "whatsapp", farmer_id)
        return self.chats[farmer_id]

    def receive(self, farmer_id: str, text: str | None = None, voice_note: str | None = None,
                language: str = "hi") -> dict:
        tr = self._chat(farmer_id)
        heard = text or ""
        kind = "text"
        if voice_note is not None:
            kind = "voice"
            heard = self.asr.transcribe(voice_note, language)["text"] if self.asr else voice_note
        tr.add("farmer", heard, kind=kind)
        out = self.handler(farmer_id, tr.session_id, heard, False)
        tr.add("saathi", out.get("reply", ""), tool_calls=[c["tool"] for c in out.get("tool_calls", [])])
        return {**out, "transcript": tr.turns}


class WhatsAppCloud:
    API = "https://graph.facebook.com/v21.0"

    def __init__(self, token: str, phone_id: str):
        self.token, self.phone_id = token, phone_id

    def send(self, to: str, text: str) -> dict:
        r = httpx.post(f"{self.API}/{self.phone_id}/messages", headers={"Authorization": f"Bearer {self.token}"},
                       json={"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text[:4096]}},
                       timeout=10)
        r.raise_for_status()
        return r.json()
