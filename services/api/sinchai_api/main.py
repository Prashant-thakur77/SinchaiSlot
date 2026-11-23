"""SinchaiSlot platform API (FastAPI).

Run: uv run uvicorn sinchai_api.main:app --port 8000
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel
from sinchai_channels.ivr import SimulatedIVR
from sinchai_channels.ussd import SimulatedUSSD
from sinchai_channels.whatsapp import SimulatedWhatsApp
from sinchai_rasid.reports import to_csv, write_pdf
from sinchai_schemas import constants as C
from sinchai_speech.adapters import make_asr, make_tts

from . import db, ledger_service, state, tools
from .agents import hisaab as hisaab_agent
from .agents import operator, saathi
from .settings import ROOT, settings

AUTOPLAY = {"on": False, "speed": 60.0}


def _turn(farmer_id: str, session_id: str, text: str, opening: bool) -> dict:
    return saathi.handle(session_id, farmer_id, text, channel=session_id.split("-")[0], opening=opening)


S = settings()
ASR = make_asr(S.speech_provider, S.speech_asr_url, S.speech_api_key)
TTS = make_tts(S.speech_provider, S.speech_tts_url, S.speech_api_key)
IVR = SimulatedIVR(_turn, asr=None, tts=TTS)
WA = SimulatedWhatsApp(_turn, asr=ASR)
USSD = SimulatedUSSD(_turn)


async def _ticker():
    while True:
        await asyncio.sleep(0.5)
        if AUTOPLAY["on"]:
            st = state.get_state()
            if st.clock.hour >= 18:
                AUTOPLAY["on"] = False
                continue
            await asyncio.to_thread(st.advance, AUTOPLAY["speed"] * 0.5 / 60, 20.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    outdated = db.schema_outdated()
    db.init_db()
    from . import bridge
    bridge.start()
    with db.session() as s:
        empty = s.query(db.Farmer).count() == 0
    if empty or outdated:  # first run, or a database from an older version: build the demo data afresh
        from .seed import seed
        await asyncio.to_thread(seed, verbose=False)
    await asyncio.to_thread(state.get_state)
    from . import cluster
    await asyncio.to_thread(cluster.neighbours)  # plans P2 and P3 and sends P2's plan to its edge
    task = asyncio.create_task(_ticker())
    yield
    task.cancel()


app = FastAPI(title="SinchaiSlot API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_hits: dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.url.path != "/api/events":
        ip = request.client.host if request.client else "?"
        q = _hits[ip]
        now = time.monotonic()
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= S.rate_limit_per_min * 10 and ip not in ("127.0.0.1", "testclient"):
            return JSONResponse({"detail": "rate limit"}, status_code=429)
        q.append(now)
    return await call_next(request)


def role_from(authorization: str | None = Header(None)) -> str:
    if authorization and authorization.removeprefix("Bearer ").strip() == S.api_token:
        return "operator"
    return "public"


def require_operator(role: str = Depends(role_from)) -> str:
    if role != "operator":
        raise HTTPException(401, "operator token required")
    return role


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {"ok": True, "llm": S.llm_provider, "speech": S.speech_provider, "db": db.engine().dialect.name}


@app.get("/api/proof")
def proof() -> dict:
    return state.load_proof()


@app.get("/api/constants")
def constants() -> dict:
    return C.as_json()


@app.get("/api/state")
def get_state() -> dict:
    return state.get_state().snapshot()


@app.get("/api/village")
def village(pump: str = "P1") -> dict:
    with db.session() as s:
        farmers = {f.id: f for f in s.query(db.Farmer).all()}
        q = s.query(db.Plot)
        plots = (q if pump == "all" else q.filter(db.Plot.pump_id == pump)).all()
        pumps = s.query(db.Pump).all()
        sellers = s.query(db.Seller).all()
        bookings = {b.plot_id: b for b in s.query(db.Booking).filter(db.Booking.day == state.get_state().day).all()}
        feats = []
        for p in plots:
            f = farmers[p.farmer_id]
            b = bookings.get(p.id)
            feats.append({"type": "Feature", "geometry": p.geojson, "properties": {
                "plot_id": p.id, "pump_id": p.pump_id, "farmer_id": f.id, "farmer": f.display_name, "tenant": f.tenant, "owner": f.owner,
                "crop": p.crop, "stage": p.stage, "area_ha": p.area_ha, "need_m3": p.need_m3,
                "booking": b.status if b else None, "slot": f"{b.slot_start}-{b.slot_end}" if b and b.slot_start else None,
                "language": f.language}})
        return {
            "plots": {"type": "FeatureCollection", "features": feats},
            "pumps": [{"id": x.id, "name": x.name, "lon": x.lon, "lat": x.lat, "kwp": x.kwp, "operator": x.operator}
                      for x in pumps],
            "sellers": [{"id": x.id, "name": x.display_name, "kind": x.kind, "lon": x.lon, "lat": x.lat,
                         "rate_rs_per_h": x.rate_rs_per_h} for x in sellers],
            "farmers": [{"id": f.id, "name": f.display_name, "tenant": f.tenant, "owner": f.owner,
                         "language": f.language} for f in farmers.values()],
            "label": "SIMULATED village on REAL weather",
        }


@app.get("/api/bookings")
def bookings(day: str | None = None) -> list[dict]:
    d = day or state.get_state().day
    with db.session() as s:
        fs = {f.id: f for f in s.query(db.Farmer).all()}
        ps = {p.id: p for p in s.query(db.Plot).all()}
        out = []
        for b in s.query(db.Booking).filter(db.Booking.day == d).order_by(db.Booking.slot_start).all():
            f, p = fs.get(b.farmer_id), ps.get(b.plot_id)
            out.append({"id": b.id, "pump_id": b.pump_id, "farmer_id": b.farmer_id, "farmer": f.display_name if f else b.farmer_id,
                        "tenant": bool(f and f.tenant), "language": f.language if f else "hi",
                        "crop": p.crop if p else None, "slot_start": b.slot_start, "slot_end": b.slot_end,
                        "m3": b.m3_requested, "m3_delivered": round(b.m3_delivered, 1), "price_rs": b.price_rs,
                        "status": b.status, "paid": b.paid, "channel": b.channel})
        return out


@app.get("/api/issues")
def issues() -> list[dict]:
    with db.session() as s:
        return [{"id": i.id, "farmer_id": i.farmer_id, "kind": i.kind, "note": i.note, "status": i.status,
                 "at": i.created_at.isoformat()} for i in s.query(db.Issue).order_by(db.Issue.id.desc()).limit(30).all()]


@app.get("/api/farmers/{farmer_id}")
def farmer(farmer_id: str) -> dict:
    from .agents.runtime import recall
    with db.session() as s:
        f = s.get(db.Farmer, farmer_id)
        if f is None:
            raise HTTPException(404)
        plots = s.query(db.Plot).filter(db.Plot.farmer_id == farmer_id).all()
        bs = s.query(db.Booking).filter(db.Booking.farmer_id == farmer_id).all()
        return {"id": f.id, "name": f.display_name, "tenant": f.tenant, "language": f.language,
                "plots": [{"id": p.id, "crop": p.crop, "stage": p.stage, "area_ha": p.area_ha, "need_m3": p.need_m3}
                          for p in plots],
                "bookings": [{"id": b.id, "slot": [b.slot_start, b.slot_end], "m3": b.m3_requested,
                              "status": b.status, "paid": b.paid} for b in bs],
                "memory": recall(farmer_id)}


# ---------------------------------------------------------------------------
# Demo control
# ---------------------------------------------------------------------------

class AdvanceIn(BaseModel):
    minutes: float = 10


class RunToIn(BaseModel):
    hhmm: str


class AutoplayIn(BaseModel):
    on: bool = True
    speed: float = 60.0  # simulated minutes per real minute... per 30 s tick scaled below


@app.post("/api/demo/reset")
def demo_reset(reseed: bool = False) -> dict:
    AUTOPLAY["on"] = False
    if reseed:
        from .seed import seed
        seed(verbose=False)
    else:
        from .seed import restore_snapshot
        restore_snapshot()
    st = state.reset_state()
    from .agents import runtime
    runtime.SESSIONS.clear()
    return st.snapshot()


@app.post("/api/demo/advance")
def demo_advance(inp: AdvanceIn) -> dict:
    st = state.get_state()
    st.advance(max(0.0, min(inp.minutes, 720.0)))
    return st.snapshot()


@app.post("/api/demo/run_to")
def demo_run_to(inp: RunToIn) -> dict:
    st = state.get_state()
    target = datetime.fromisoformat(f"{st.day}T{inp.hhmm}")
    mins = (target - st.clock).total_seconds() / 60
    if mins > 0:
        st.advance(mins)
    return st.snapshot()


@app.post("/api/demo/autoplay")
def demo_autoplay(inp: AutoplayIn) -> dict:
    AUTOPLAY.update(on=inp.on, speed=max(1.0, min(inp.speed, 600.0)))
    return AUTOPLAY


@app.get("/api/events")
async def events(request: Request):
    st = state.get_state()
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    with st.bus.lock:
        st.bus.subscribers.append(q)

    async def gen():
        try:
            yield "retry: 2000\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"event: {ev.kind}\ndata: {json.dumps({'ts': ev.ts, **ev.data}, default=str)}\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            with st.bus.lock:
                if q in st.bus.subscribers:
                    st.bus.subscribers.remove(q)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/events/recent")
def events_recent(kind: str | None = None, limit: int = 100) -> list[dict]:
    st = state.get_state()
    evs = [e for e in st.bus.log if kind is None or e.kind == kind]
    return [{"ts": e.ts, "kind": e.kind, **e.data} for e in evs[-limit:]]


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------

class MissedCallIn(BaseModel):
    farmer_id: str


class SayIn(BaseModel):
    session_id: str
    text: str | None = None
    dtmf: str | None = None


class WaIn(BaseModel):
    farmer_id: str
    text: str | None = None
    voice_note: str | None = None


class UssdPress(BaseModel):
    session_id: str
    key: str


@app.post("/api/channels/ivr/missed_call")
def ivr_missed(inp: MissedCallIn) -> dict:
    return IVR.missed_call(inp.farmer_id)


@app.post("/api/channels/ivr/say")
def ivr_say(inp: SayIn) -> dict:
    if inp.session_id not in IVR.calls:
        raise HTTPException(404, "no such call")
    return IVR.farmer_says(inp.session_id, inp.text, inp.dtmf)


@app.post("/api/channels/whatsapp")
def wa(inp: WaIn) -> dict:
    return WA.receive(inp.farmer_id, inp.text, inp.voice_note)


@app.post("/api/channels/ussd/dial")
def ussd_dial(inp: MissedCallIn) -> dict:
    return USSD.dial(inp.farmer_id)


@app.post("/api/channels/ussd/press")
def ussd_press(inp: UssdPress) -> dict:
    if inp.session_id not in USSD.sessions:
        raise HTTPException(404)
    return USSD.press(inp.session_id, inp.key)


@app.get("/api/channels/callbacks")
def callbacks() -> list[dict]:
    return state.get_state().callbacks


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

class AgentIn(BaseModel):
    text: str
    session_id: str = "web"
    farmer_id: str | None = None
    step: int = 0
    observation: str = ""


@app.post("/api/agents/saathi")
def agent_saathi(inp: AgentIn) -> dict:
    if not inp.farmer_id:
        raise HTTPException(400, "farmer_id required")
    return saathi.handle(inp.session_id, inp.farmer_id, inp.text, channel="web")


@app.post("/api/agents/copilot")
def agent_copilot(inp: AgentIn) -> dict:
    return operator.copilot(inp.session_id, inp.text, inp.step, inp.observation)


@app.post("/api/agents/planner")
def agent_planner(inp: AgentIn) -> dict:
    return operator.planner(inp.text)


@app.post("/api/agents/auditor")
def agent_auditor(inp: AgentIn) -> dict:
    return operator.auditor(inp.text)


@app.post("/api/agents/hisaab")
def agent_hisaab(inp: AgentIn) -> dict:
    from .agents import runtime
    run = runtime.Run("hisaab", "web", "funder", "rules", inp.text, "en")
    r = hisaab_agent.answer(inp.text)
    run._record("hisaab_ask", {"question": inp.text}, {k: v for k, v in r.items() if k != "rows"}, False, None,
                None, 0.0)
    return {**run.finish(r["answer"]), **r}


@app.get("/api/tools")
def list_tools() -> list[dict]:
    return tools.describe()


class ToolIn(BaseModel):
    args: dict[str, Any] = {}
    confirm: bool = False


@app.post("/api/tools/{name}")
def call_tool(name: str, inp: ToolIn, role: str = Depends(role_from)) -> dict:
    t = tools.REGISTRY.get(name)
    if t is None:
        raise HTTPException(404, "unknown tool")
    ctx = tools.ToolContext(role="operator" if role == "operator" else "farmer",
                            user_ref=inp.args.get("farmer_id"), channel="api")
    if role != "operator" and "farmer" not in t.roles:
        raise HTTPException(401, "operator token required for this tool")
    if t.confirm and not inp.confirm:
        return {"needs_confirmation": True, "tool": name, "args": inp.args}
    from .agents import runtime
    run = runtime.Run("api", "api", ctx.user_ref, "direct", f"{name} {json.dumps(inp.args)}", "en")
    r = run.call(name, inp.args, ctx, confirmed=True if t.confirm else None)
    run.finish(json.dumps(r, default=str)[:500], "error" if "error" in r else "ok")
    if "error" in r:
        raise HTTPException(400, r["error"])
    return r


# ---------------------------------------------------------------------------
# Drive (Schneider Altivar Solar, simulated in the demo)
# ---------------------------------------------------------------------------

class FaultIn(BaseModel):
    fault: str = "OHF"


class DryIn(BaseModel):
    on: bool = True


@app.get("/api/drive")
def drive() -> dict:
    st = state.get_state()
    t = st.edge.drive.read_telemetry()
    from sinchai_devices import altivar_map as M
    return {**t.model_dump(), "pv_kw_available": round(st.pv_now(), 3), "extras": st.model.ui_extras(),
            "label": "Schneider Altivar Solar - simulated", "unverified_registers": M.unverified(),
            "meter": {"k": st.edge.meter.k, "k_rse": st.edge.meter.k_rse}}


@app.get("/api/drive/calibration")
def drive_calibration() -> dict:
    """Drive-as-meter curve: estimated flow vs power, and a simulated flow-meter calibration set."""
    import numpy as np
    from sinchai_devices.physics import default_pump
    pm = default_pump()
    p = np.linspace(0, pm.rated_kw, 40)
    rng = np.random.default_rng(3)
    pts = []
    for kw in np.linspace(pm.p_cutoff_kw + 0.3, pm.rated_kw, 14):
        q = float(pm.flow_for_power(kw))
        pts.append({"kw": round(float(kw), 3), "estimate_m3h": round(q, 2),
                    "meter_m3h": round(q * 0.95 * (1 + rng.normal(0, 0.03)), 2)})
    est = np.array([x["estimate_m3h"] for x in pts])
    met = np.array([x["meter_m3h"] for x in pts])
    k = float(est @ met / (est @ est))
    return {"curve": [{"kw": round(float(a), 3), "m3h": round(float(pm.flow_for_power(a)), 2)} for a in p],
            "calibration_points": pts, "k": round(k, 4), "cutoff_kw": round(pm.p_cutoff_kw, 3),
            "label": "Pump curve model; calibration points SIMULATED (flow meter not fitted in the demo)"}


@app.get("/api/drive/faults")
def drive_faults() -> list[dict]:
    from sinchai_devices import altivar_map as M
    return [{"mnemonic": f.mnemonic, "name": f.name, "lft": f.lft_value, "description": f.description,
             "verified": f.verified} for f in M.faults().values()]


@app.get("/api/drive/registers")
def drive_registers() -> list[dict]:
    from sinchai_devices import altivar_map as M
    return [{"mnemonic": r.mnemonic, "address": r.address, "scale": r.scale, "unit": r.unit, "verified": r.verified,
             "description": r.description[:160]} for r in M.registers().values()]


@app.post("/api/drive/fault")
def drive_fault(inp: FaultIn) -> dict:
    st = state.get_state()
    st.model.inject_fault(inp.fault)
    st.bus.publish(st.clock.isoformat(), "edge", {"type": "drive_fault", "fault": inp.fault, "injected": True})
    return drive()


@app.post("/api/drive/dry_run")
def drive_dry(inp: DryIn) -> dict:
    state.get_state().model.set_dry_run(inp.on)
    return drive()


@app.post("/api/drive/reset")
def drive_reset() -> dict:
    st = state.get_state()
    st.edge.drive.reset_fault()
    st.edge.tripped = None
    return drive()


# ---------------------------------------------------------------------------
# Rasid ledger
# ---------------------------------------------------------------------------

@app.get("/api/ledger")
def ledger(limit: int = 50, offset: int = 0, kind: str | None = None) -> dict:
    limit = max(1, min(limit, 500))
    with db.session() as s:
        q = s.query(db.LedgerRow)
        if kind:
            q = q.filter(db.LedgerRow.kind == kind)
        total = q.count()
        rows = q.order_by(db.LedgerRow.seq.desc()).offset(offset).limit(limit).all()
        return {"total": total, "rows": [ledger_service.row_to_dict(r) for r in rows],
                "summary": tools.call("ledger_summary", {}, tools.ToolContext())}


@app.get("/api/ledger/verify")
def ledger_verify() -> dict:
    with db.session() as s:
        return ledger_service.verify(s)


@app.get("/api/ledger/audit")
def ledger_audit() -> dict:
    return tools.call("audit_ledger", {}, tools.ToolContext())


@app.get("/api/ledger/export.csv")
def ledger_csv() -> Response:
    with db.session() as s:
        return Response(to_csv(ledger_service.receipts(s)), media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=rasid-ledger.csv"})


@app.get("/api/ledger/report.pdf")
def ledger_pdf() -> Response:
    import tempfile
    from pathlib import Path
    with db.session() as s, tempfile.TemporaryDirectory() as d:
        p = write_pdf(ledger_service.receipts(s), Path(d) / "report.pdf")
        return Response(p.read_bytes(), media_type="application/pdf",
                        headers={"Content-Disposition": "attachment; filename=rasid-funder-report.pdf"})


# ---------------------------------------------------------------------------
# Cluster, Pump Passport, soil card
# ---------------------------------------------------------------------------

def _tool(name: str, args: dict | None = None) -> dict:
    try:
        return tools.call(name, args or {}, tools.ToolContext(role="system"))
    except (tools.ToolError, ValueError) as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/cluster")
def cluster_view() -> dict:
    return _tool("cluster_overview")


@app.get("/api/cluster/suggest")
def cluster_suggest(pump: str | None = None) -> dict:
    return _tool("suggest_transfers", {"pump_id": pump})


@app.get("/api/cluster/transfer_options/{booking_id}")
def cluster_transfer_options(booking_id: str) -> dict:
    return _tool("transfer_options", {"booking_id": booking_id})


@app.get("/api/cluster/recharge")
def cluster_recharge(pump: str | None = None, share: float = 1.0) -> dict:
    return _tool("recharge_plan", {"pump_id": pump, "offset_share": share})


@app.get("/api/pumps/{pump_id}/passport")
def pump_passport(pump_id: str) -> dict:
    return _tool("pump_passport", {"pump_id": pump_id})


@app.get("/api/pumps/{pump_id}/passport.pdf")
def pump_passport_pdf(pump_id: str) -> Response:
    import tempfile
    from pathlib import Path

    from sinchai_rasid.passport import write_pdf as passport_pdf
    pp = _tool("pump_passport", {"pump_id": pump_id})
    with tempfile.TemporaryDirectory() as d:
        p = passport_pdf(pp, Path(d) / "passport.pdf")
        return Response(Path(p).read_bytes(), media_type="application/pdf",
                        headers={"Content-Disposition": f"attachment; filename=pump-passport-{pump_id}.pdf"})


class SoilReadIn(BaseModel):
    image_b64: str | None = None
    media_type: str = "image/png"
    sample: bool = False


@app.get("/api/soil-card/sample.png")
def soil_sample() -> Response:
    from .agents.soil_card import SAMPLE
    return Response(SAMPLE.read_bytes(), media_type="image/png")


@app.post("/api/soil-card/read")
def soil_read(inp: SoilReadIn) -> dict:
    import base64

    from .agents import soil_card
    if inp.sample:
        img = soil_card.SAMPLE.read_bytes()
    elif inp.image_b64:
        try:
            img = base64.b64decode(inp.image_b64.split(",")[-1], validate=False)
        except ValueError as e:
            raise HTTPException(400, "bad image") from e
        if len(img) > 6_000_000:
            raise HTTPException(413, "image too large")
    else:
        raise HTTPException(400, "send image_b64 or sample=true")
    if inp.media_type not in ("image/png", "image/jpeg", "image/webp"):
        raise HTTPException(415, "png, jpeg or webp only")
    return soil_card.read(img, inp.media_type)


@app.get("/api/ledger/claim")
def ledger_claim(from_date: str = "2024-01-01", to_date: str = "2024-12-31", funder: str = "CSR funder") -> dict:
    return tools.call("claim_pack", {"funder": funder, "from_date": from_date, "to_date": to_date}, tools.ToolContext())


# ---------------------------------------------------------------------------
# Agent traces
# ---------------------------------------------------------------------------

@app.get("/api/traces")
def traces(limit: int = 50, agent: str | None = None) -> list[dict]:
    with db.session() as s:
        q = s.query(db.AgentRun)
        if agent:
            q = q.filter(db.AgentRun.agent == agent)
        runs = q.order_by(db.AgentRun.created_at.desc()).limit(max(1, min(limit, 200))).all()
        out = []
        for r in runs:
            calls = s.query(db.ToolCallRow).filter(db.ToolCallRow.run_id == r.id).order_by(db.ToolCallRow.id).all()
            out.append({"id": r.id, "agent": r.agent, "channel": r.channel, "user_ref": r.user_ref,
                        "provider": r.provider, "input": r.input_text, "output": r.output_text, "status": r.status,
                        "language": r.language, "latency_ms": round(r.latency_ms, 1), "at": r.created_at.isoformat(),
                        "tool_calls": [{"name": c.name, "args": c.args, "result": c.result, "confirm": c.needs_confirmation,
                                        "confirmed": c.confirmed, "error": c.error, "ms": round(c.latency_ms, 1)}
                                       for c in calls]})
        return out


_STORY: dict = {}


@app.get("/api/story")
def story() -> dict:
    """Live content for the landing story: Saathi's real offer to Ramesh (rendered from the planner,
    cached), the latest plan-change callback if the day has run past 13:40, and the latest receipt."""
    from .agents import i18n
    from .agents.saathi import _offer_text

    st = state.get_state()
    if st.day not in _STORY:
        r = tools.call("find_slots", {"farmer_id": "H01"}, tools.ToolContext(role="system"))
        offer = None
        if r.get("available"):
            offer = {"mai": _offer_text("mai", r, "Ramesh"), "en": _offer_text("en", r, "Ramesh"),
                     "greet": i18n.say("greet", "mai", name="Ramesh"), "numbers": {k: r[k] for k in (
                         "need_m3", "expected_m3_p50", "carry_over_m3", "window_start", "window_end", "price_rs",
                         "diesel_equivalent_rs")}}
        _STORY[st.day] = offer
    with db.session() as s:
        last = s.query(db.LedgerRow).filter(db.LedgerRow.kind == "water").order_by(db.LedgerRow.seq.desc()).first()
        receipt = ledger_service.row_to_dict(last) if last else None
    return {"day": st.day, "offer": _STORY[st.day], "callbacks": st.callbacks[-3:], "diffs": st.diffs[-1:],
            "receipt": receipt}


@app.get("/api/evals")
def evals() -> dict:
    p = ROOT / "reports" / "evals.json"
    return json.loads(p.read_text()) if p.exists() else {"status": "run `make evals`"}


@app.get("/api/budget")
def budget() -> dict:
    return tools.call("budget_status", {}, tools.ToolContext())


