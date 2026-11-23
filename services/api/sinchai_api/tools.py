"""Typed tool layer shared by every agent, the HTTP API and the MCP server.

Each tool has a Pydantic input model, the roles allowed to call it, and a `confirm` flag. A tool
with `confirm=True` spends money, water or energy: when an agent calls it, the runtime does not run
it but returns a confirmation request; it runs only after the farmer or Saur Mitra says yes.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from sinchai_edge.controller import unlock_code
from sinchai_jal.budget import awd_irrigate
from sinchai_planner.optimizer import Request, solve
from sinchai_rasid.audit import audit
from sinchai_rasid.reports import claim_pack, summarise
from sinchai_schemas import constants as C

from . import db, ledger_service
from .settings import settings
from .state import N_SLOTS, get_state

Role = Literal["farmer", "operator", "funder", "planner", "system"]


@dataclass
class ToolContext:
    role: Role = "system"
    user_ref: str | None = None  # farmer id for farmer role
    channel: str = "api"
    language: str = "hi"


@dataclass
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    fn: Callable[[ToolContext, Any], dict]
    roles: tuple[str, ...]
    confirm: bool = False

    def schema(self) -> dict:
        s = self.input_model.model_json_schema()
        s.pop("title", None)
        s["additionalProperties"] = False
        return s


REGISTRY: dict[str, Tool] = {}


def tool(name: str, description: str, roles: tuple[str, ...], confirm: bool = False):
    def deco(fn):
        model = fn.__annotations__["inp"]
        if isinstance(model, str):
            model = globals()[model]
        REGISTRY[name] = Tool(name, description, model, fn, roles, confirm)
        return fn
    return deco


class ToolError(Exception):
    pass


def call(name: str, args: dict, ctx: ToolContext) -> dict:
    t = REGISTRY.get(name)
    if t is None:
        raise ToolError(f"unknown tool {name}")
    if ctx.role != "system" and ctx.role not in t.roles:
        raise ToolError(f"role {ctx.role} may not call {name}")
    inp = t.input_model.model_validate(args)
    if ctx.role == "farmer" and hasattr(inp, "farmer_id"):
        # A farmer can only act on their own account, whatever the model or the message asks for.
        if getattr(inp, "farmer_id", None) not in (None, ctx.user_ref):
            raise ToolError("farmers can only act on their own bookings")
        inp.farmer_id = ctx.user_ref
    return t.fn(ctx, inp)


# ===========================================================================
# Helpers
# ===========================================================================

def _tariff() -> float:
    return C.get("sinchaislot_tariff_rs_per_m3")


def _diesel_rs_per_m3() -> float:
    return C.get("diesel_water_rs_per_hour") / C.get("diesel_pump_flow_m3h")


def _farmer_plot(s, farmer_id: str, plot_id: str | None) -> db.Plot:
    q = s.query(db.Plot).filter(db.Plot.farmer_id == farmer_id)
    if plot_id:
        q = q.filter(db.Plot.id == plot_id)
    p = q.order_by(db.Plot.need_m3.desc()).first()
    if p is None:
        raise ToolError("no plot found for this farmer")
    return p


def _booking_view(s, b: db.Booking) -> dict:
    return {"booking_id": b.id, "day": b.day, "slot_start": b.slot_start, "slot_end": b.slot_end,
            "m3": b.m3_requested, "m3_delivered": round(b.m3_delivered, 1), "price_rs": b.price_rs,
            "status": b.status, "paid": b.paid, "plot_id": b.plot_id}


# ===========================================================================
# Saathi (farmer) tools
# ===========================================================================

class FindSlotsIn(BaseModel):
    farmer_id: str | None = None
    plot_id: str | None = None
    m3: float | None = Field(None, description="Water wanted in m3; defaults to the crop's FAO-56 need")


@tool("find_slots", "Find when the shared solar pump can water a plot today, sized to the crop's need.",
      ("farmer", "operator", "system"))
def find_slots(ctx: ToolContext, inp: FindSlotsIn) -> dict:
    """Solves a what-if plan with the new request and keeps it as an offer: if the farmer says yes
    before the plan changes, exactly this plan is adopted, so what was offered is what is booked."""
    import uuid

    st = get_state()
    with db.session() as s:
        p = _farmer_plot(s, inp.farmer_id, inp.plot_id)
        f = s.get(db.Farmer, p.farmer_id)
        cap = p.need_m3
        m3 = min(inp.m3, cap) if inp.m3 else cap
        if m3 <= 0.5:
            return {"available": False, "reason": "crop_need_met", "need_m3": round(cap, 1), "plot_id": p.id,
                    "crop": p.crop}
        prio = 1.0 + (0.5 if p.stage == "mid" else 0.0)
        new = Request("NEW", p.farmer_id, m3, prio, due_today=True, tenant=bool(f.tenant))
        with st.lock:
            plan_inp = st.build_input(s, freeze_from_now=st.slot_index() > 0, extra=[new])
            display = st._display_scen
            version = st.plan_version
    plan = solve(plan_inp)
    ks = [sp.slot for sp in plan.slots if sp.action == "req:NEW"]
    if not ks:
        return {"available": False, "reason": "no_sun_left_today", "need_m3": round(m3, 1), "plot_id": p.id,
                "crop": p.crop, "next": "tomorrow morning"}
    token = uuid.uuid4().hex[:10]
    st.offers[token] = {"plan": plan, "inp": plan_inp, "display": display, "version": version,
                        "farmer_id": p.farmer_id, "plot_id": p.id, "m3": round(m3, 1)}
    today = plan.served_m3["NEW"]["P50"]
    return {"available": True, "offer_token": token, "plot_id": p.id, "crop": p.crop, "stage": p.stage,
            "need_m3": round(m3, 1), "window_start": st.slot_label(min(ks)), "window_end": st.slot_label(max(ks) + 1),
            "slots": [st.slot_label(k) for k in ks],
            "expected_m3_p50": round(today, 1), "expected_m3_p10": round(plan.served_m3["NEW"]["P10"], 1),
            "carry_over_m3": round(max(m3 - today, 0.0), 1),
            "price_rs": round(m3 * _tariff(), 0), "diesel_equivalent_rs": round(m3 * _diesel_rs_per_m3(), 0)}


class QuoteIn(BaseModel):
    farmer_id: str | None = None
    plot_id: str | None = None
    m3: float | None = None


@tool("quote_price", "Quote the price of solar water per m3 and compare with diesel.", ("farmer", "operator", "system"))
def quote_price(ctx: ToolContext, inp: QuoteIn) -> dict:
    with db.session() as s:
        m3 = inp.m3
        if m3 is None and inp.farmer_id:
            m3 = _farmer_plot(s, inp.farmer_id, inp.plot_id).need_m3
    m3 = m3 or 30.0
    return {"m3": round(m3, 1), "tariff_rs_per_m3": _tariff(), "price_rs": round(m3 * _tariff(), 0),
            "diesel_rs_per_m3": round(_diesel_rs_per_m3(), 2), "diesel_price_rs": round(m3 * _diesel_rs_per_m3(), 0),
            "saving_rs": round(m3 * (_diesel_rs_per_m3() - _tariff()), 0)}


class BookIn(BaseModel):
    farmer_id: str | None = None
    plot_id: str | None = None
    m3: float | None = None
    offer_token: str | None = Field(None, description="Token from find_slots; books exactly the offered slots")


@tool("book_slot", "Book solar water for a plot today (needs the farmer's confirmation).",
      ("farmer", "operator", "system"), confirm=True)
def book_slot(ctx: ToolContext, inp: BookIn) -> dict:
    st = get_state()
    offer = st.offers.pop(inp.offer_token, None) if inp.offer_token else None
    with db.session() as s:
        if offer is not None:
            inp.plot_id, m3_fixed = offer["plot_id"], offer["m3"]
        p = _farmer_plot(s, inp.farmer_id, inp.plot_id)
        m3 = m3_fixed if offer is not None else (min(inp.m3, p.need_m3) if inp.m3 else p.need_m3)
        if m3 <= 0.5:
            raise ToolError("the crop's water need is already met")
        existing = s.query(db.Booking).filter(db.Booking.plot_id == p.id, db.Booking.day == st.day,
                                              db.Booking.status.in_(["confirmed", "paid", "running"])).first()
        if existing:
            return {"booked": False, "reason": "already_booked", **_booking_view(s, existing)}
        n = s.query(db.Booking).filter(db.Booking.pump_id == "P1", db.Booking.day == st.day).count() + 1
        while s.get(db.Booking, f"B{st.day[5:7]}{st.day[8:10]}{n:03d}") is not None:
            n += 1
        b = db.Booking(id=f"B{st.day[5:7]}{st.day[8:10]}{n:03d}", farmer_id=p.farmer_id, plot_id=p.id, pump_id="P1",
                       day=st.day, m3_requested=round(m3, 1), price_rs=round(m3 * _tariff(), 0), status="confirmed",
                       channel=ctx.channel)
        s.add(b)
        s.commit()
        bid = b.id
    if offer is not None and offer["version"] == st.plan_version:
        plan, pinp = offer["plan"], offer["inp"]
        for sp in plan.slots:
            if sp.action == "req:NEW":
                sp.action, sp.household = f"req:{bid}", p.farmer_id
        plan.served_m3[bid] = plan.served_m3.pop("NEW", {})
        for r in pinp.requests:
            if r.id == "NEW":
                r.id = bid
        st.adopt(plan, pinp, f"new booking {bid}", offer["display"])
        honoured = True
    else:
        st.solve_plan(reason=f"new booking {bid}", freeze_from_now=st.slot_index() > 0)
        honoured = False
    with db.session() as s:
        b = s.get(db.Booking, bid)
        return {"booked": True, "offer_honoured": honoured,
                "expected_today_m3": round(st.plan.served_m3.get(bid, {}).get("P50", 0.0), 1), **_booking_view(s, b)}


class BookingRef(BaseModel):
    farmer_id: str | None = None
    booking_id: str | None = None


@tool("cancel_slot", "Cancel a booking (needs confirmation).", ("farmer", "operator", "system"), confirm=True)
def cancel_slot(ctx: ToolContext, inp: BookingRef) -> dict:
    st = get_state()
    with db.session() as s:
        q = s.query(db.Booking).filter(db.Booking.status.in_(["confirmed", "paid"]))
        if inp.booking_id:
            q = q.filter(db.Booking.id == inp.booking_id)
        if inp.farmer_id:
            q = q.filter(db.Booking.farmer_id == inp.farmer_id)
        b = q.first()
        if b is None:
            raise ToolError("no open booking to cancel")
        b.status = "cancelled"
        refund = b.price_rs if b.paid else 0.0
        f = s.get(db.Farmer, b.farmer_id)
        f.balance_rs += refund
        s.commit()
        bid = b.id
    st.solve_plan(reason=f"cancelled {bid}")
    return {"cancelled": True, "booking_id": bid, "refund_to_balance_rs": refund}


class FarmerRef(BaseModel):
    farmer_id: str | None = None


@tool("my_bookings", "List the farmer's bookings and slot times.", ("farmer", "operator", "system"))
def my_bookings(ctx: ToolContext, inp: FarmerRef) -> dict:
    with db.session() as s:
        bs = s.query(db.Booking).filter(db.Booking.farmer_id == inp.farmer_id).order_by(db.Booking.created_at).all()
        return {"bookings": [_booking_view(s, b) for b in bs]}


@tool("get_balance", "Money due and credit balance for a farmer.", ("farmer", "operator", "system"))
def get_balance(ctx: ToolContext, inp: FarmerRef) -> dict:
    with db.session() as s:
        f = s.get(db.Farmer, inp.farmer_id)
        if f is None:
            raise ToolError("unknown farmer")
        due = sum(b.price_rs for b in s.query(db.Booking).filter(db.Booking.farmer_id == f.id,
                                                                db.Booking.paid.is_(False),
                                                                db.Booking.status != "cancelled").all())
        return {"due_rs": round(due, 0), "credit_rs": round(f.balance_rs, 0)}


class PayIn(BaseModel):
    farmer_id: str | None = None
    booking_id: str | None = None


@tool("pay_link", "UPI payment link for a booking (test mode).", ("farmer", "operator", "system"))
def pay_link(ctx: ToolContext, inp: PayIn) -> dict:
    with db.session() as s:
        q = s.query(db.Booking).filter(db.Booking.paid.is_(False), db.Booking.status.in_(["confirmed"]))
        if inp.booking_id:
            q = q.filter(db.Booking.id == inp.booking_id)
        if inp.farmer_id:
            q = q.filter(db.Booking.farmer_id == inp.farmer_id)
        b = q.first()
        if b is None:
            raise ToolError("nothing to pay")
        vpa = settings().upi_vpa
        return {"booking_id": b.id, "amount_rs": b.price_rs, "test_mode": True,
                "upi_link": f"upi://pay?pa={vpa}&pn=SinchaiSlot&am={b.price_rs:.2f}&cu=INR&tn={b.id}"}


class RecordPaymentIn(BaseModel):
    booking_id: str
    method: Literal["upi", "cash"] = "cash"


@tool("record_payment", "Mark a booking paid (UPI callback or cash to the Saur Mitra) and issue the unlock code.",
      ("operator", "system", "farmer"), confirm=True)
def record_payment(ctx: ToolContext, inp: RecordPaymentIn) -> dict:
    st = get_state()
    with db.session() as s:
        b = s.get(db.Booking, inp.booking_id)
        if b is None:
            raise ToolError("unknown booking")
        if ctx.role == "farmer" and b.farmer_id != ctx.user_ref:
            raise ToolError("not your booking")
        b.paid = True
        b.status = "paid"
        counter = st.edge.last_counter + 1 if st.edge else 0
        b.unlock_counter = counter
        s.commit()
        code = unlock_code(settings().edge_secret.encode(), b.pump_id, b.id, b.m3_requested, counter)
    if st.edge:
        st.edge.enter_code(inp.booking_id, code)
    st._push_edge_plan()
    return {"paid": True, "booking_id": inp.booking_id, "method": inp.method, "unlock_code": code,
            "sms": f"SinchaiSlot: booking {inp.booking_id} paid. Code {code}"}


@tool("check_schemes", "Which government schemes this farmer may use (from cited scheme rules only).",
      ("farmer", "operator", "system"))
def check_schemes(ctx: ToolContext, inp: FarmerRef) -> dict:
    with db.session() as s:
        f = s.get(db.Farmer, inp.farmer_id)
        area_acres = sum(p.area_ha for p in s.query(db.Plot).filter(db.Plot.farmer_id == f.id).all()) / 0.404686
    out = [{
        "scheme": "Bihar diesel subsidy (Kharif 2026)",
        "rule": f"Rs {C.get('bihar_diesel_subsidy_rs_per_l')}/L, Rs {C.get('bihar_diesel_subsidy_rs_per_acre_irrigation')} "
                f"per acre per irrigation, up to {C.get('bihar_diesel_subsidy_max_irrigations')} irrigations and "
                f"{C.get('bihar_diesel_subsidy_max_acres')} acres",
        "status": "kharif only; needs geo-tagged photo and petrol receipt",
        "max_rs_this_season": round(min(area_acres, C.get("bihar_diesel_subsidy_max_acres"))
                                    * C.get("bihar_diesel_subsidy_rs_per_acre_irrigation")
                                    * C.get("bihar_diesel_subsidy_max_irrigations"), 0),
        "note": "Tenant eligibility not stated in the source; confirm with the block agriculture office.",
        "source": C.entry("bihar_diesel_subsidy_rs_per_l").source_url,
    }]
    if f.owner or not f.tenant:
        out.append({"scheme": "PM-KUSUM standalone solar pump", "status": "land-owning farmers may apply",
                    "source": C.entry("kusum_standalone_pumps").source_url})
    return {"farmer_id": f.id, "tenant": f.tenant, "schemes": out}


class IssueIn(BaseModel):
    farmer_id: str | None = None
    kind: Literal["no_water", "low_flow", "leak", "payment", "other"] = "other"
    note: str = ""


@tool("report_issue", "Report a problem with the pump, water or payment.", ("farmer", "operator", "system"))
def report_issue(ctx: ToolContext, inp: IssueIn) -> dict:
    with db.session() as s:
        i = db.Issue(farmer_id=inp.farmer_id, pump_id="P1", kind=inp.kind, note=inp.note[:500])
        s.add(i)
        s.commit()
        iid = i.id
    get_state().bus.publish(get_state().clock.isoformat(), "issue", {"id": iid, "kind": inp.kind})
    return {"issue_id": iid, "status": "open", "assigned_to": "Saur Mitra"}


@tool("explain_plan_change", "Why the farmer's water time changed in the latest plan.", ("farmer", "operator", "system"))
def explain_plan_change(ctx: ToolContext, inp: FarmerRef) -> dict:
    st = get_state()
    for d in reversed(st.diffs):
        for c in d["changes"]:
            if c.get("household") == inp.farmer_id:
                return {"at": d["at"], "reason": d["reason"], "change": c}
    return {"change": None}


# ===========================================================================
# Surya Planner tools
# ===========================================================================

class Empty(BaseModel):
    pass


@tool("run_forecast", "Today's P10/P50/P90 solar power forecast per 30-minute slot.", ("planner", "operator", "system", "funder"))
def run_forecast(ctx: ToolContext, inp: Empty) -> dict:
    st = get_state()
    sc = st.scenarios_now()
    return {"day": st.day, "labels": [st.slot_label(k) for k in range(N_SLOTS)],
            **{s.name: [round(float(x), 3) for x in s.pv_kw] for s in sc}}


@tool("solve_plan", "Re-solve today's plan from now with the latest forecast and bookings.", ("planner", "operator", "system"))
def solve_plan_tool(ctx: ToolContext, inp: Empty) -> dict:
    return get_state().solve_plan(reason="manual re-plan", freeze_from_now=True)


class WhatIfIn(BaseModel):
    cloud_factor: float = Field(0.5, ge=0.0, le=1.5, description="Multiply forecast sun by this in the window")
    from_hhmm: str = "13:00"
    to_hhmm: str = "15:00"


@tool("what_if", "Simulate a change in sun over a window and show how the plan would change (does not apply it).",
      ("planner", "operator", "system", "funder"))
def what_if(ctx: ToolContext, inp: WhatIfIn) -> dict:
    from dataclasses import replace

    from sinchai_planner.optimizer import Scenario
    from sinchai_planner.replan import explain_diff
    st = get_state()
    a = st.slot_index(datetime.fromisoformat(f"{st.day}T{inp.from_hhmm}"))
    b = st.slot_index(datetime.fromisoformat(f"{st.day}T{inp.to_hhmm}"))
    scen = []
    for s in st.plan_input.scenarios:
        pv = s.pv_kw.copy()
        pv[a:b] *= inp.cloud_factor
        scen.append(Scenario(s.name, s.prob, pv))
    plan = solve(replace(st.plan_input, scenarios=scen))
    diff = explain_diff(st.plan, plan, st.plan_input.scenarios, scen)
    return {"water_m3_p50_before": round(st.plan.total("water"), 1), "water_m3_p50_after": round(plan.total("water"), 1),
            "mill_kwh_before": round(st.plan.total("mill"), 2), "mill_kwh_after": round(plan.total("mill"), 2),
            "battery_kwh_after": round(plan.total("battery"), 2), "changes": [c.__dict__ for c in diff]}


@tool("explain_diff", "The latest plan change and the reason for each moved slot.", ("planner", "operator", "system", "farmer"))
def explain_diff_tool(ctx: ToolContext, inp: Empty) -> dict:
    st = get_state()
    return st.diffs[-1] if st.diffs else {"changes": []}


# ===========================================================================
# Saur Mitra Copilot tools
# ===========================================================================

@tool("today_plan", "Today's slots, bookings and expected energy use.", ("operator", "planner", "system", "funder"))
def today_plan(ctx: ToolContext, inp: Empty) -> dict:
    snap = get_state().snapshot()
    return {"day": snap["day"], "clock": snap["clock"], "summary": snap["summary"],
            "slots": [{k: v for k, v in s.items() if k in ("start", "action", "farmer", "booking_id")} for s in snap["slots"]]}


@tool("cash_book", "Today's money: paid, due, by method, and the Saur Mitra's share.", ("operator", "system"))
def cash_book(ctx: ToolContext, inp: Empty) -> dict:
    st = get_state()
    with db.session() as s:
        bs = s.query(db.Booking).filter(db.Booking.day == st.day, db.Booking.status != "cancelled").all()
        paid = sum(b.price_rs for b in bs if b.paid)
        due = sum(b.price_rs for b in bs if not b.paid)
    return {"day": st.day, "paid_rs": paid, "due_rs": due, "bookings": len(bs),
            "saur_mitra_share_rs": round(paid * C.get("saur_mitra_revenue_share"), 0)}


@tool("drive_status", "Live Altivar Solar drive telemetry (simulated drive in the demo).", ("operator", "planner", "system", "funder"))
def drive_status(ctx: ToolContext, inp: Empty) -> dict:
    st = get_state()
    t = st.edge.drive.read_telemetry()
    return {**t.model_dump(), "pv_kw_available": round(st.pv_now(), 3)}


class DiagnoseIn(BaseModel):
    fault_code: str | None = Field(None, description="Drive fault mnemonic, e.g. OHF, ULF; empty = read from drive")
    symptoms: str = ""
    step: int = 0
    observation: str = ""


@tool("diagnose", "Step-by-step fault diagnosis from the drive fault code and the Altivar manuals.",
      ("operator", "system"))
def diagnose(ctx: ToolContext, inp: DiagnoseIn) -> dict:
    from .agents.copilot import diagnose_step
    code = inp.fault_code
    if not code:
        code = get_state().edge.drive.read_telemetry().fault
    return diagnose_step(code, inp.step, inp.observation, inp.symptoms)


class MaintenanceIn(BaseModel):
    action: str
    note: str = ""
    fault: str | None = None


@tool("log_maintenance", "Log a maintenance action on the pump (needs confirmation).", ("operator", "system"), confirm=True)
def log_maintenance(ctx: ToolContext, inp: MaintenanceIn) -> dict:
    with db.session() as s:
        m = db.Maintenance(pump_id="P1", action=inp.action[:64], note=inp.note[:500], fault=inp.fault)
        s.add(m)
        s.commit()
        return {"logged": True, "id": m.id}


class PartIn(BaseModel):
    part: str
    quantity: int = 1


@tool("request_part", "Request a spare part from the operator's store (needs confirmation).", ("operator", "system"),
      confirm=True)
def request_part(ctx: ToolContext, inp: PartIn) -> dict:
    return {"requested": True, "part": inp.part, "quantity": inp.quantity, "status": "queued for the FPO store"}


@tool("reset_fault", "Reset the drive fault after the cause is fixed (needs confirmation).", ("operator", "system"),
      confirm=True)
def reset_fault(ctx: ToolContext, inp: Empty) -> dict:
    st = get_state()
    st.edge.drive.reset_fault()
    st.edge.tripped = None
    t = st.edge.drive.read_telemetry()
    return {"state": t.state, "fault": t.fault}


class InjectIn(BaseModel):
    fault: str = "OHF"


@tool("inject_fault", "Demo only: inject a documented Altivar fault into the simulated drive.", ("system", "operator"))
def inject_fault(ctx: ToolContext, inp: InjectIn) -> dict:
    st = get_state()
    st.model.inject_fault(inp.fault)
    return {"injected": inp.fault}


class DryIn(BaseModel):
    on: bool = True


@tool("set_dry_run", "Demo only: make the simulated well run dry (or recover).", ("system", "operator"))
def set_dry_run(ctx: ToolContext, inp: DryIn) -> dict:
    get_state().model.set_dry_run(inp.on)
    return {"dry_run": inp.on}


# ===========================================================================
# Jal Prahari
# ===========================================================================

@tool("budget_status", "Cluster groundwater budget: cap, used and remaining this season.",
      ("operator", "planner", "funder", "system", "farmer"))
def budget_status(ctx: ToolContext, inp: Empty) -> dict:
    st = get_state()
    d = date.fromisoformat(st.day)
    from sinchai_jal.budget import season_of
    sea = season_of(d)
    cap = st.budget.season_cap(sea)
    used = st.budget.used_m3[sea]
    return {"season": sea, "season_cap_m3": round(cap, 0), "used_m3": round(used, 0),
            "remaining_m3": round(st.budget.remaining(d), 0), "used_fraction": round(used / cap, 3),
            "alert": used / cap >= 0.8, "category": C.get("samastipur_block_category"),
            "category_status": "UNVERIFIED"}


class AwdIn(BaseModel):
    field_water_level_mm: float
    stage: str = "mid"


@tool("awd_advice", "Alternate wetting and drying advice for paddy from the field water tube reading.",
      ("farmer", "operator", "system"))
def awd_advice(ctx: ToolContext, inp: AwdIn) -> dict:
    return {"irrigate": awd_irrigate(inp.field_water_level_mm, inp.stage), "threshold_mm": -150}


# ===========================================================================
# Rasid
# ===========================================================================

class PeriodIn(BaseModel):
    from_date: str | None = None
    to_date: str | None = None


def _period_receipts(s, inp: PeriodIn):
    rs = ledger_service.receipts(s)
    if inp.from_date:
        rs = [r for r in rs if r.start[:10] >= inp.from_date]
    if inp.to_date:
        rs = [r for r in rs if r.start[:10] <= inp.to_date]
    return rs


@tool("ledger_summary", "Totals from verified receipts: water, energy, diesel and CO2 avoided, farmers served.",
      ("funder", "operator", "planner", "system"))
def ledger_summary(ctx: ToolContext, inp: PeriodIn) -> dict:
    with db.session() as s:
        return summarise(_period_receipts(s, inp))


@tool("verify_ledger", "Check the hash chain of the whole ledger.", ("funder", "operator", "system"))
def verify_ledger(ctx: ToolContext, inp: Empty) -> dict:
    with db.session() as s:
        return ledger_service.verify(s)


@tool("audit_ledger", "Run the anomaly audit (physical rules + Isolation Forest) on receipts.", ("funder", "operator", "system"))
def audit_ledger(ctx: ToolContext, inp: PeriodIn) -> dict:
    with db.session() as s:
        f = audit(_period_receipts(s, inp))
    return {"findings": [x.__dict__ for x in f[:50]], "n_findings": len(f)}


class ClaimIn(BaseModel):
    funder: str = "CSR funder"
    from_date: str
    to_date: str


@tool("claim_pack", "Build an Anudan Meter claim pack (measurement-and-verification certificate).", ("funder", "operator", "system"))
def claim_pack_tool(ctx: ToolContext, inp: ClaimIn) -> dict:
    with db.session() as s:
        cp = claim_pack(ledger_service.receipts(s), inp.funder, date.fromisoformat(inp.from_date),
                        date.fromisoformat(inp.to_date))
    cp["receipt_hashes"] = cp["receipt_hashes"][:20] + (["..."] if len(cp["receipt_hashes"]) > 20 else [])
    return cp


# ===========================================================================
# Hisaab and Paani Khata
# ===========================================================================

class SqlIn(BaseModel):
    sql: str = Field(..., description="One read-only SELECT over tables ledger, bookings, plots, pumps, sellers")


@tool("query_ledger_sql", "Run one read-only, row-limited SELECT over the ledger and bookings.", ("funder", "operator", "planner", "system"))
def query_ledger_sql(ctx: ToolContext, inp: SqlIn) -> dict:
    from .agents.hisaab import run_readonly_sql
    return run_readonly_sql(inp.sql)


class AskIn(BaseModel):
    question: str


@tool("hisaab_ask", "Answer a question about the ledger in plain language with numbers.", ("funder", "operator", "planner", "system"))
def hisaab_ask(ctx: ToolContext, inp: AskIn) -> dict:
    from .agents.hisaab import answer
    return answer(inp.question)


@tool("list_sellers", "Paani Khata: diesel and electric water sellers for overflow when solar is full.",
      ("farmer", "operator", "system"))
def list_sellers(ctx: ToolContext, inp: Empty) -> dict:
    with db.session() as s:
        return {"sellers": [{"id": x.id, "name": x.display_name, "kind": x.kind, "rate_rs_per_h": x.rate_rs_per_h,
                             "rs_per_m3": round(x.rate_rs_per_h / x.flow_m3h, 2), "available": x.available}
                            for x in s.query(db.Seller).all()]}


class SellerBookIn(BaseModel):
    farmer_id: str | None = None
    seller_id: str
    hours: float = Field(1.0, gt=0, le=8)


@tool("book_seller", "Book overflow water from a Paani Khata seller (needs confirmation).", ("farmer", "operator", "system"),
      confirm=True)
def book_seller(ctx: ToolContext, inp: SellerBookIn) -> dict:
    with db.session() as s:
        x = s.get(db.Seller, inp.seller_id)
        if x is None or not x.available:
            raise ToolError("seller not available")
        x.agent_bookings += 1
        s.commit()
        return {"booked": True, "seller": x.display_name, "hours": inp.hours, "price_rs": round(x.rate_rs_per_h * inp.hours, 0),
                "note": "Overflow booking; not counted as solar water in Rasid."}


# ===========================================================================
# Cluster: neighbouring pumps, transfers, data health, passport
# ===========================================================================

@tool("cluster_overview", "All pumps in the cluster: today's water, open bookings, faults, data health, water quality.",
      ("operator", "planner", "funder", "system"))
def cluster_overview(ctx: ToolContext, inp: Empty) -> dict:
    from . import cluster
    return cluster.overview()


class TransferRef(BaseModel):
    booking_id: str


@tool("transfer_options", "Which neighbouring pumps can reach a booking's plot and what each would deliver today.",
      ("operator", "farmer", "system"))
def transfer_options_tool(ctx: ToolContext, inp: TransferRef) -> dict:
    from . import cluster
    _own_booking(ctx, inp.booking_id)
    try:
        return cluster.transfer_options(inp.booking_id)
    except ValueError as e:
        raise ToolError(str(e)) from e


class TransferIn(BaseModel):
    booking_id: str
    to_pump: str


@tool("transfer_booking", "Move a booking to a neighbouring pump that can reach the plot (needs confirmation).",
      ("operator", "farmer", "system"), confirm=True)
def transfer_booking(ctx: ToolContext, inp: TransferIn) -> dict:
    from . import cluster
    _own_booking(ctx, inp.booking_id)
    try:
        return cluster.transfer(inp.booking_id, inp.to_pump)
    except ValueError as e:
        raise ToolError(str(e)) from e


class PumpRef(BaseModel):
    pump_id: str | None = None


@tool("suggest_transfers", "When a pump is down or full, the best neighbouring pump for each of its open bookings.",
      ("operator", "planner", "system"))
def suggest_transfers_tool(ctx: ToolContext, inp: PumpRef) -> dict:
    from . import cluster
    return cluster.suggest_transfers(inp.pump_id)


@tool("pump_health", "Data-health monitor: is each pump still reporting, late, silent or stalled.",
      ("operator", "funder", "planner", "system"))
def pump_health(ctx: ToolContext, inp: PumpRef) -> dict:
    from . import cluster
    with db.session() as s:
        ids = [inp.pump_id] if inp.pump_id else [p.id for p in s.query(db.Pump).order_by(db.Pump.id).all()]
    return {"pumps": [cluster.health(i) for i in ids]}


def _own_booking(ctx: ToolContext, booking_id: str) -> None:
    if ctx.role != "farmer":
        return
    with db.session() as s:
        b = s.get(db.Booking, booking_id)
        if b is None or b.farmer_id != ctx.user_ref:
            raise ToolError("not your booking")


@tool("pump_passport", "Pump Passport: utilisation, uptime, faults, receipts, repayment record and credit scorecard.",
      ("funder", "operator", "planner", "system"))
def pump_passport(ctx: ToolContext, inp: PumpRef) -> dict:
    from sinchai_rasid.passport import PumpMeta, passport

    from . import cluster
    st = get_state()
    pid = inp.pump_id or "P1"
    as_of = date.fromisoformat(st.day)
    with db.session() as s:
        p = s.get(db.Pump, pid)
        if p is None:
            raise ToolError("unknown pump")
        receipts = ledger_service.receipts(s)
        verified = ledger_service.verify(s).get("ok", False)
        mt = s.query(db.Maintenance).filter(db.Maintenance.pump_id == pid).all()
        faults = [{"code": m.fault, "at": m.created_at.date().isoformat(), "downtime_h": m.downtime_h}
                  for m in mt if m.fault]
        credits = s.query(db.Credit).filter(db.Credit.pump_id == pid, db.Credit.paid_on.isnot(None)).all()
        meta = PumpMeta(p.id, p.name, p.kwp, p.operator)
    first = min((r.start[:10] for r in receipts if r.pump_id == pid), default=None)
    span = max((as_of - date.fromisoformat(first)).days, 1) if first else 1
    op_hours = min(span, 365) * (C.get("operator_end_hour") - C.get("operator_start_hour"))
    down = sum(f["downtime_h"] for f in faults)
    uptime = max(0.0, 1 - down / op_hours) if op_hours else None
    on_time = sum(1 for c in credits if c.paid_on <= c.due) / len(credits) if credits else None
    health = cluster.health(pid)["status"]
    out = passport(meta, receipts, as_of, uptime=uptime, faults=faults, repayment_on_time=on_time,
                   ledger_verified=verified, data_health=health)
    out["fault_log"] = sorted(faults, key=lambda f: f["at"], reverse=True)
    out["downtime_h"] = round(down, 1)
    out["after_harvest_credits"] = len(credits)
    out["water_quality"] = cluster.card(pid, cluster.BOREWELL_EC_DSM.get(pid, 0.6)).to_dict()
    out["labels"] = {"receipts": "SIMULATED operation on REAL weather", "faults": "SIMULATED history",
                     "credits": "SIMULATED history"}
    return out


@tool("water_quality", "Water-quality card for a pump's borewell (EC/TDS probe) and which crops it suits.",
      ("farmer", "operator", "funder", "system"))
def water_quality(ctx: ToolContext, inp: PumpRef) -> dict:
    from . import cluster
    pid = inp.pump_id or "P1"
    return cluster.card(pid, cluster.BOREWELL_EC_DSM.get(pid, 0.6)).to_dict()


class RechargeIn(BaseModel):
    pump_id: str | None = None
    offset_share: float = Field(1.0, gt=0, le=2)


@tool("recharge_plan", "Recharge pairing: structures that put back what a pump (or the cluster) takes out each year.",
      ("funder", "operator", "planner", "system"))
def recharge_plan(ctx: ToolContext, inp: RechargeIn) -> dict:
    from sinchai_jal.recharge import pair
    st = get_state()
    as_of = date.fromisoformat(st.day)
    since = date(as_of.year - 1, as_of.month, as_of.day).isoformat()
    with db.session() as s:
        q = s.query(db.LedgerRow).filter(db.LedgerRow.kind == "water", db.LedgerRow.start >= since)
        if inp.pump_id:
            q = q.filter(db.LedgerRow.pump_id == inp.pump_id)
        m3 = sum(r.m3 for r in q.all())
    out = pair(m3, inp.offset_share)
    out["scope"] = inp.pump_id or "cluster"
    out["period"] = f"{since} to {st.day}"
    return out


# ===========================================================================
# Harvest-linked repayment
# ===========================================================================

def _history(s, farmer_id: str):
    from sinchai_rasid.credit import Repayment
    return [Repayment(date.fromisoformat(c.due), c.amount_rs + c.fee_rs,
                      date.fromisoformat(c.paid_on) if c.paid_on else None)
            for c in s.query(db.Credit).filter(db.Credit.farmer_id == farmer_id).all()]


class HarvestIn(BaseModel):
    farmer_id: str | None = None
    booking_id: str | None = None


@tool("harvest_offer", "Can this booking be paid partly after harvest, how much now and how much later.",
      ("farmer", "operator", "system"))
def harvest_offer(ctx: ToolContext, inp: HarvestIn) -> dict:
    from sinchai_rasid.credit import offer
    st = get_state()
    with db.session() as s:
        q = s.query(db.Booking).filter(db.Booking.paid.is_(False), db.Booking.status == "confirmed")
        if inp.booking_id:
            q = q.filter(db.Booking.id == inp.booking_id)
        if inp.farmer_id:
            q = q.filter(db.Booking.farmer_id == inp.farmer_id)
        b = q.first()
        if b is None:
            raise ToolError("no unpaid booking")
        p = s.get(db.Plot, b.plot_id)
        o = offer(b.price_rs, p.crop if p.crop in ("wheat", "maize", "paddy", "potato", "veg_summer") else "wheat",
                  date.fromisoformat(st.day), _history(s, b.farmer_id))
        return {"booking_id": b.id, "farmer_id": b.farmer_id, **o.to_dict(),
                "history": [{"due": r.due.isoformat(), "amount_rs": r.amount_rs,
                             "paid_on": r.paid_on.isoformat() if r.paid_on else None, "on_time": r.on_time()}
                            for r in _history(s, b.farmer_id)]}


@tool("pay_after_harvest", "Take the pay-now part in cash or UPI and record the rest as due after harvest (needs confirmation).",
      ("farmer", "operator", "system"), confirm=True)
def pay_after_harvest(ctx: ToolContext, inp: HarvestIn) -> dict:
    o = harvest_offer(ctx, inp)
    if not o["eligible"]:
        raise ToolError(o["reason_en"])
    st = get_state()
    with db.session() as s:
        b = s.get(db.Booking, o["booking_id"])
        s.add(db.Credit(farmer_id=b.farmer_id, booking_id=b.id, pump_id=b.pump_id, amount_rs=o["after_harvest_rs"],
                        fee_rs=o["fee_rs"], due=o["due"], created_on=st.day))
        s.commit()
    paid = record_payment(ctx, RecordPaymentIn(booking_id=o["booking_id"], method="cash"))
    return {**paid, "pay_now_rs": o["pay_now_rs"], "after_harvest_rs": o["after_harvest_rs"], "fee_rs": o["fee_rs"],
            "due": o["due"], "reason_en": o["reason_en"], "reason_hi": o["reason_hi"]}


# ===========================================================================
# Soil Health Card and Bharat-VISTAAR
# ===========================================================================

class SoilIn(BaseModel):
    farmer_id: str | None = None
    plot_id: str | None = None
    texture: str | None = None
    ph: float | None = None
    ec_dsm: float | None = None
    oc_pct: float | None = None
    n_kg_ha: float | None = None
    p_kg_ha: float | None = None
    k_kg_ha: float | None = None
    s_ppm: float | None = None
    zn_ppm: float | None = None
    card_no: str | None = None


@tool("apply_soil_card", "Set a plot's soil from its Soil Health Card values; changes how often its crop is watered.",
      ("farmer", "operator", "system"))
def apply_soil_card(ctx: ToolContext, inp: SoilIn) -> dict:
    from sinchai_planner.soil import SoilCard, apply
    with db.session() as s:
        p = _farmer_plot(s, inp.farmer_id, inp.plot_id)
        card = SoilCard(**inp.model_dump(exclude={"farmer_id", "plot_id"}))
        crop = p.crop if p.crop in ("wheat", "maize", "paddy", "potato", "veg_summer") else "wheat"
        res = apply(card, crop)
        p.taw_mm_per_m = res["taw_mm_per_m"]
        p.soil_card = res["card"]
        s.commit()
        return {"plot_id": p.id, **res}


class AdviceIn(BaseModel):
    farmer_id: str | None = None
    question: str


@tool("vistaar_handoff", "Hand an agronomy question (pests, fertiliser, seed, prices) to Bharat-VISTAAR with the farm context.",
      ("farmer", "operator", "system"))
def vistaar_handoff(ctx: ToolContext, inp: AdviceIn) -> dict:
    from sinchai_channels.vistaar import TOPICS, Handoff, adapter, classify
    with db.session() as s:
        f = s.get(db.Farmer, inp.farmer_id) if inp.farmer_id else None
        p = s.query(db.Plot).filter(db.Plot.farmer_id == inp.farmer_id).first() if inp.farmer_id else None
        topic = classify(inp.question)
        h = Handoff(question=inp.question[:500], topic=topic, language=f.language if f else ctx.language,
                    farmer_ref=inp.farmer_id or "anon", crop=p.crop if p else None, stage=p.stage if p else None,
                    soil=p.soil_card if p else None)
    rec = adapter().handoff(h)
    en, hi = TOPICS[topic]
    return {**rec, "topic_en": en, "topic_hi": hi}


def describe() -> list[dict]:
    return [{"name": t.name, "description": t.description, "roles": list(t.roles), "confirm": t.confirm,
             "input_schema": t.schema()} for t in REGISTRY.values()]


def timed_call(name: str, args: dict, ctx: ToolContext) -> tuple[dict, float, str | None]:
    t0 = time.perf_counter()
    try:
        r = call(name, args, ctx)
        return r, (time.perf_counter() - t0) * 1000, None
    except (ToolError, ValueError) as e:
        return {"error": str(e)}, (time.perf_counter() - t0) * 1000, str(e)
