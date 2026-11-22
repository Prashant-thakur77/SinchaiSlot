"""Saur Mitra Copilot chat, Surya Planner agent and Rasid Auditor: thin conversational layers over
the typed tools. Every call is traced; confirm-tools go through the same gate as Saathi."""

from __future__ import annotations

import re

from ..tools import ToolContext
from . import runtime
from .nlu import parse

FAULT_RE = re.compile(r"\b([A-Z]{2,4}[0-9]?)\b")


def copilot(session_id: str, text: str, step: int = 0, observation: str = "") -> dict:
    sess = runtime.get_session(session_id, "copilot", "operator", "saur_mitra", "pwa")
    p = parse(text, "hi")
    run = runtime.Run("copilot", "pwa", "saur_mitra", "rules", text, p.language)
    ctx = ToolContext(role="operator", user_ref="saur_mitra", channel="pwa", language=p.language)
    if sess.pending is not None and p.intent in ("yes", "no"):
        pend, sess.pending = sess.pending, None
        if p.intent == "no":
            return run.finish("Cancelled.")
        r = run.call(pend.tool, pend.args, ctx, confirmed=True)
        return {**run.finish(f"Done: {pend.tool}"), "result": r}
    tl = text.lower()
    codes = [c for c in FAULT_RE.findall(text) if c in _fault_codes()]
    if codes or any(k in tl for k in ("fault", "फ़ॉल्ट", "फॉल्ट", "error", "band", "बंद", "trip", "diagnos")):
        r = run.call("diagnose", {"fault_code": codes[0] if codes else None, "symptoms": text, "step": step,
                                  "observation": observation}, ctx)
        msg = r.get("instruction_hi") or r.get("instruction_en") or ""
        if r.get("done") and r.get("next_tool") == "reset_fault":
            sess.pending = runtime.Pending("reset_fault", {}, {})
            run.propose("reset_fault", {})
            msg += " | Reset the drive now? (haan / nahin)"
        return {**run.finish(msg), "diagnosis": r}
    if any(k in tl for k in ("paisa", "पैसा", "cash", "hisab", "हिसाब", "कमाई")):
        r = run.call("cash_book", {}, ctx)
        return {**run.finish(f"Aaj jama Rs {int(r['paid_rs'])}, baaki Rs {int(r['due_rs'])}, "
                             f"aapka hissa Rs {int(r['saur_mitra_share_rs'])}."), "result": r}
    if any(k in tl for k in ("drive", "ड्राइव", "status", "pump", "पंप")):
        r = run.call("drive_status", {}, ctx)
        return {**run.finish(f"Drive {r['state']}, {r['freq_hz']} Hz, {r['power_kw']} kW, fault {r['fault'] or '-'}"),
                "result": r}
    if any(k in tl for k in ("budget", "बजट", "bhujal", "भूजल")):
        r = run.call("budget_status", {}, ctx)
        return {**run.finish(f"{r['season']} budget: {int(r['used_m3'])} of {int(r['season_cap_m3'])} m3 used."),
                "result": r}
    r = run.call("today_plan", {}, ctx)
    nxt = [s for s in r["slots"] if s["action"] != "idle" and s["start"] >= r["clock"]][:4]
    lst = ", ".join(f"{s['start']} {s['farmer'] or s['action']}" for s in nxt)
    return {**run.finish(f"Aage: {lst or 'koi slot nahin'}."), "result": r}


def _fault_codes() -> set[str]:
    from sinchai_devices import altivar_map as M
    return set(M.faults())


def planner(text: str) -> dict:
    """Surya Planner agent: forecast, what-if, re-plan and explain, from a plain request."""
    run = runtime.Run("surya_planner", "web", "planner", "rules", text, "en")
    ctx = ToolContext(role="planner", user_ref="planner", channel="web", language="en")
    tl = text.lower()
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(?:-|to|से)\s*(\d{1,2})(?::(\d{2}))?", tl)
    f = re.search(r"(\d{1,3})\s*%", tl)
    if any(k in tl for k in ("what if", "cloud", "बादल", "agar")) and m:
        a = f"{int(m.group(1)):02d}:{m.group(2) or '00'}"
        b = f"{int(m.group(3)):02d}:{m.group(4) or '00'}"
        factor = 1 - int(f.group(1)) / 100 if f else 0.5
        r = run.call("what_if", {"cloud_factor": max(0.0, factor), "from_hhmm": a, "to_hhmm": b}, ctx)
        return {**run.finish(f"With {int((1 - factor) * 100)}% less sun {a}-{b}: water {r['water_m3_p50_before']} -> "
                             f"{r['water_m3_p50_after']} m3, mill {r['mill_kwh_before']} -> {r['mill_kwh_after']} kWh; "
                             f"{len(r['changes'])} slot changes."), "result": r}
    if any(k in tl for k in ("why", "explain", "diff", "क्यों")):
        r = run.call("explain_diff", {}, ctx)
        lines = [c["reason_en"] for c in r.get("changes", [])]
        return {**run.finish("; ".join(lines) or "No changes in the latest plan."), "result": r}
    if any(k in tl for k in ("replan", "re-plan", "solve")):
        r = run.call("solve_plan", {}, ctx)
        return {**run.finish(f"Plan v{r['version']} solved in {r['solve_s']} s, {len(r['changes'])} changes."), "result": r}
    r = run.call("run_forecast", {}, ctx)
    tot = {k: round(sum(r[k]) * 0.5, 1) for k in ("P10", "P50", "P90")}
    return {**run.finish(f"Today's solar energy: P10 {tot['P10']} kWh, P50 {tot['P50']} kWh, P90 {tot['P90']} kWh."),
            "result": r}


def auditor(text: str) -> dict:
    run = runtime.Run("rasid_auditor", "web", "funder", "rules", text, "en")
    ctx = ToolContext(role="funder", user_ref="funder", channel="web", language="en")
    v = run.call("verify_ledger", {}, ctx)
    a = run.call("audit_ledger", {}, ctx)
    s = run.call("ledger_summary", {}, ctx)
    msg = (f"Ledger {'verified' if v['ok'] else 'BROKEN at ' + str(v['first_bad_seq'])} over {v['checked']} receipts. "
           f"{s['m3']} m3 solar water, {s['diesel_l_avoided']} L diesel and {s['co2_kg_avoided']} kg CO2 avoided. "
           f"{a['n_findings']} audit findings.")
    return {**run.finish(msg), "verify": v, "audit": a, "summary": s}
