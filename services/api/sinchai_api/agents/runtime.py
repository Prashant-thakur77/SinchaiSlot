"""Agent runtime: typed tool calls, a trace of every run, and the confirmation gate.

Agents plan, explain and talk; deterministic code executes. A tool marked `confirm` is never run on
the model's say-so: the runtime stores it as a pending action, reads it back to the user in their
language, and runs it only when the user's next turn is a clear yes (decided by the deterministic
NLU, not by the model).

Providers
  rules     - offline, deterministic (default; no key needed)
  anthropic - optional hosted LLM with tool use (set LLM_PROVIDER=anthropic and its API key)
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .. import db, tools
from ..settings import settings


@dataclass
class Pending:
    tool: str
    args: dict
    summary: dict


@dataclass
class Session:
    id: str
    agent: str
    role: str
    user_ref: str | None
    language: str = "hi"
    channel: str = "api"
    pending: Pending | None = None
    misses: int = 0
    history: list[dict] = field(default_factory=list)  # provider conversation (anthropic)
    last: dict = field(default_factory=dict)


SESSIONS: dict[str, Session] = {}


def get_session(session_id: str, agent: str, role: str, user_ref: str | None, channel: str = "api",
                language: str | None = None) -> Session:
    s = SESSIONS.get(session_id)
    if s is None:
        s = Session(session_id, agent, role, user_ref, language or "hi", channel)
        SESSIONS[session_id] = s
    return s


class Run:
    """One agent turn, written to the trace store."""

    def __init__(self, agent: str, channel: str, user_ref: str | None, provider: str, text: str, language: str):
        self.id = "run_" + uuid.uuid4().hex[:16]
        self.t0 = time.perf_counter()
        self.calls: list[dict] = []
        self.agent, self.channel, self.user_ref, self.provider = agent, channel, user_ref, provider
        self.text, self.language = text, language
        with db.session() as s:
            s.add(db.AgentRun(id=self.id, agent=agent, channel=channel, user_ref=user_ref, provider=provider,
                              input_text=text[:2000], language=language))
            s.commit()

    def call(self, name: str, args: dict, ctx: tools.ToolContext, confirmed: bool | None = None) -> dict:
        result, ms, err = tools.timed_call(name, args, ctx)
        self._record(name, args, result, False, confirmed, err, ms)
        return result

    def propose(self, name: str, args: dict) -> None:
        self._record(name, args, {"status": "awaiting_confirmation"}, True, None, None, 0.0)

    def _record(self, name, args, result, needs_conf, confirmed, err, ms) -> None:
        self.calls.append({"tool": name, "args": args, "result": result, "needs_confirmation": needs_conf,
                           "confirmed": confirmed, "error": err, "latency_ms": round(ms, 1)})
        with db.session() as s:
            s.add(db.ToolCallRow(run_id=self.id, name=name, args=json.loads(json.dumps(args, default=str)),
                                 result=json.loads(json.dumps(result, default=str)), needs_confirmation=needs_conf,
                                 confirmed=confirmed, error=err, latency_ms=ms))
            s.commit()

    def finish(self, reply: str, status: str = "ok") -> dict:
        ms = (time.perf_counter() - self.t0) * 1000
        with db.session() as s:
            r = s.get(db.AgentRun, self.id)
            r.output_text, r.status, r.latency_ms = reply[:4000], status, ms
            s.commit()
        return {"run_id": self.id, "reply": reply, "tool_calls": self.calls, "latency_ms": round(ms, 1),
                "provider": self.provider, "language": self.language}


# ---------------------------------------------------------------------------
# Memory per farmer across seasons
# ---------------------------------------------------------------------------

def remember(farmer_id: str, key: str, value: Any) -> None:
    from datetime import datetime

    with db.session() as s:
        m = s.get(db.Memory, (farmer_id, key))
        if m is None:
            s.add(db.Memory(farmer_id=farmer_id, key=key, value=value))
        else:
            m.value, m.updated_at = value, datetime.utcnow()
        s.commit()


def recall(farmer_id: str) -> dict:
    with db.session() as s:
        return {m.key: m.value for m in s.query(db.Memory).filter(db.Memory.farmer_id == farmer_id).all()}


# ---------------------------------------------------------------------------
# Hosted LLM provider (optional)
# ---------------------------------------------------------------------------

def anthropic_available() -> bool:
    if settings().llm_provider != "anthropic":
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def llm_turn(system: str, session: Session, user_text: str, tool_names: list[str], run: Run,
                ctx: tools.ToolContext, max_steps: int = 6) -> tuple[str, Pending | None]:
    """Manual tool-use loop with the hosted LLM. Confirm-tools are intercepted and returned as pending."""
    import anthropic

    client = anthropic.Anthropic()
    tdefs = [{"name": t.name, "description": t.description, "input_schema": t.schema(), "strict": True}
             for t in (tools.REGISTRY[n] for n in tool_names)]
    session.history.append({"role": "user", "content": f"<farmer_message>\n{user_text}\n</farmer_message>"})
    pending: Pending | None = None
    for _ in range(max_steps):
        resp = client.beta.messages.create(
            model=settings().anthropic_model,
            max_tokens=16000,
            system=system,
            tools=tdefs,
            messages=session.history,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if resp.stop_reason == "refusal":
            return "", None
        session.history.append({"role": "assistant", "content": resp.content})
        uses = [b for b in resp.content if b.type == "tool_use"]
        if resp.stop_reason != "tool_use" or not uses:
            text = " ".join(b.text for b in resp.content if b.type == "text").strip()
            return text, pending
        results = []
        for u in uses:
            t = tools.REGISTRY.get(u.name)
            args = dict(u.input)
            if t is not None and t.confirm:
                pending = Pending(u.name, args, {})
                run.propose(u.name, args)
                results.append({"type": "tool_result", "tool_use_id": u.id,
                                "content": "Held for the farmer's confirmation; the system will read it back."})
            else:
                r = run.call(u.name, args, ctx)
                results.append({"type": "tool_result", "tool_use_id": u.id, "content": json.dumps(r, default=str),
                                "is_error": "error" in r})
        session.history.append({"role": "user", "content": results})
        if pending is not None:
            return "", pending
    return "", pending
