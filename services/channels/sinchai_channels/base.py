"""Channel adapters: how farmers reach Saathi.

Every channel has an interface plus a local simulator, so the full demo runs offline. Real provider
adapters are configured through .env and are never required.

Turn handler contract: `handler(farmer_id, session_id, text, opening) -> dict` with at least `reply`.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

TurnHandler = Callable[[str, str, str, bool], dict]


@dataclass
class Transcript:
    session_id: str
    channel: str
    farmer_id: str
    turns: list[dict] = field(default_factory=list)

    def add(self, who: str, text: str, **extra) -> None:
        self.turns.append({"t": round(time.time(), 3), "who": who, "text": text, **extra})


class OutboundSender(Protocol):
    def send(self, to: str, text: str) -> dict: ...


def session_id_for(channel: str, farmer_id: str, salt: str = "") -> str:
    return f"{channel}-{hashlib.sha256(f'{farmer_id}{salt}{time.time_ns()}'.encode()).hexdigest()[:10]}"
