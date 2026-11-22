"""USSD fallback (*code# menus) for phones with no data and noisy lines where voice fails.

Menu (Hindi, numeric only, fits 182-character USSD screens):
  1 पानी बुक करें   2 मेरी बुकिंग   3 दाम   4 बकाया   5 शिकायत   0 सुनीता दीदी से बात
Each choice maps to a Saathi request; confirmations use 1 = हाँ, 2 = नहीं.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .base import TurnHandler, session_id_for

MENU = "सिंचाईस्लॉट\n1 पानी बुक करें\n2 मेरी बुकिंग\n3 दाम\n4 बकाया\n5 शिकायत\n0 सुनीता दीदी"
CHOICE_TEXT = {"1": "पानी चाहिए", "2": "मेरी बुकिंग", "3": "कितना लगेगा", "4": "बकाया", "5": "शिकायत पंप खराब",
               "0": "मदद"}
USSD_MAX = 182


@dataclass
class USSDSession:
    farmer_id: str
    session_id: str
    awaiting_confirm: bool = False


@dataclass
class SimulatedUSSD:
    handler: TurnHandler
    sessions: dict[str, USSDSession] = field(default_factory=dict)

    def dial(self, farmer_id: str) -> dict:
        sid = session_id_for("ussd", farmer_id)
        self.sessions[sid] = USSDSession(farmer_id, sid)
        return {"session_id": sid, "screen": MENU, "end": False}

    def press(self, session_id: str, key: str) -> dict:
        s = self.sessions[session_id]
        text = key if s.awaiting_confirm else CHOICE_TEXT.get(key, "मदद")
        out = self.handler(s.farmer_id, session_id, text, False)
        s.awaiting_confirm = out.get("pending") is not None
        screen = out.get("reply", "")
        if len(screen) > USSD_MAX:
            screen = screen[: USSD_MAX - 1] + "…"
        return {"session_id": session_id, "screen": screen, "end": not s.awaiting_confirm, "full_reply": out.get("reply"),
                "tool_calls": out.get("tool_calls", [])}
