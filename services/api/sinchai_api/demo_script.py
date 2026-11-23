"""`make demo` / `make soak`: the scripted demo scenario, in-process, no server or keys needed.

  1. Ramesh gives a missed call; Saathi calls back in Maithili, offers a slot sized to his wheat's need
  2. Ramesh says yes; the booking is read back; he pays the Saur Mitra (cash); unlock code issued
  3. The day runs on the real held-out sun; the edge controller runs slots on the Altivar drive model
  4. At 13:40 the nowcast shows the afternoon below the forecast band: re-plan, reasons, callbacks
  5. A drive fault (OHF) is injected; the Copilot walks the Saur Mitra through the fix
  6. Rasid: receipts verified, audit run, claim pack totals

`--soak N` repeats the whole scenario N times and checks that every run gives the same plan
changes, callbacks and ledger state (determinism) and that all invariants hold.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time

from . import db, state, tools
from .agents import operator, runtime, saathi


def _p(title: str, body: str = "") -> None:
    print(f"\n== {title} ==")
    if body:
        print(body)


def run_once(verbose: bool = True) -> dict:
    from .seed import restore_snapshot

    runtime.SESSIONS.clear()
    restore_snapshot()
    st = state.reset_state()
    log = st.snapshot()
    if verbose:
        _p("Morning plan", f"{st.day} {log['clock']}  plan v{log['plan_version']}  {log['summary']}")

    r = saathi.handle("demo-ivr", "H01", "", channel="ivr", opening=True)
    if verbose:
        _p("Missed call -> Saathi calls Ramesh back", r["reply"])
    r2 = saathi.handle("demo-ivr", "H01", "हँ, बुक करू", channel="ivr")
    if verbose:
        _p("Ramesh: हँ, बुक करू", r2["reply"])
    booked = next(c for c in r2["tool_calls"] if c["tool"] == "book_slot" and c["confirmed"])
    bid = booked["result"]["booking_id"]
    pay = tools.call("record_payment", {"booking_id": bid, "method": "cash"}, tools.ToolContext(role="operator"))
    if verbose:
        _p("Sunita records cash payment", pay["sms"])

    st.advance((13 * 60 + 30) - (st.clock.hour * 60 + st.clock.minute))
    before = st.snapshot()
    st.advance(40)  # to 14:10, past the 13:40 nowcast
    after = st.snapshot()
    diff = after["diffs"][-1] if after["diffs"] else {"changes": []}
    if verbose:
        _p("13:40 nowcast: afternoon below the forecast band",
           f"plan v{before['plan_version']} -> v{after['plan_version']}\n" +
           "\n".join(" - " + c["reason_en"] for c in diff["changes"]))
        for cb in after["callbacks"]:
            print(f" phone rings: {cb['name']} ({cb['language']}): {cb['text']}")

    st.model.inject_fault("OHF")
    steps = []
    for k in range(10):
        d = operator.copilot("demo-cp", "OHF fault", step=k)
        steps.append(d["diagnosis"]["instruction_en"])
        if d["diagnosis"]["done"]:
            break
    operator.copilot("demo-cp", "haan")
    fault_after = st.edge.drive.read_telemetry().fault
    if verbose:
        _p("Copilot: OHF drive overheating, guided fix", "\n".join(f" {i + 1}. {s}" for i, s in enumerate(steps)))
        print(f" fault after reset: {fault_after}")

    st.advance((18 * 60) - (st.clock.hour * 60 + st.clock.minute))
    aud = operator.auditor("end of day audit")
    if verbose:
        _p("Rasid at end of day", aud["reply"])
    with db.session() as s:
        today = [r.receipt_id for r in s.query(db.LedgerRow).filter(db.LedgerRow.start >= st.day).all()]
        ledger_head = s.query(db.LedgerRow).order_by(db.LedgerRow.seq.desc()).first().hash
        ramesh = s.get(db.Booking, bid)
        ramesh_m3 = ramesh.m3_delivered
    sig = hashlib.sha256(json.dumps({
        "changes": [(c["kind"], c["subject"], c["old_slots"], c["new_slots"]) for c in diff["changes"]],
        "callbacks": [c["text"] for c in after["callbacks"]], "receipts": len(today),
        "ramesh_m3": round(ramesh_m3, 1), "ledger_head": ledger_head}, sort_keys=True).encode()).hexdigest()[:16]
    checks = {
        "cloud_replan_happened": after["plan_version"] > before["plan_version"] and after["cloud_applied"],
        "reasons_given": all(c["reason_en"] and c["reason_hi"] for c in diff["changes"]),
        "ramesh_booked_and_paid": ramesh.paid,
        "receipts_written": len(today) > 0,
        "ledger_verified": aud["verify"]["ok"],
        "fault_cleared": fault_after is None,
        "budget_never_exceeded": st.budget.remaining(__import__("datetime").date.fromisoformat(st.day)) >= 0,
    }
    def strip(snap: dict) -> list[dict]:
        return [{"start": x["start"], "action": x["action"], "farmer": x["farmer"]} for x in snap["slots"]]

    replay = {"day": st.day, "label": "REPLAY of the scripted demo day (real held-out sun)",
              "changes": [{k: c[k] for k in ("kind", "subject", "old_slots", "new_slots", "reason_en", "reason_hi")}
                          for c in diff["changes"]],
              "callbacks": after["callbacks"], "slots_before": strip(before), "slots_after": strip(after)}
    return {"signature": sig, "checks": checks, "replay": replay, "ramesh_m3": round(ramesh_m3, 1), "receipts_today": len(today),
            "changes": len(diff["changes"]), "callbacks": len(after["callbacks"])}


def _write_replay(replay: dict) -> None:
    """The 13:40 re-plan and callbacks, kept for the story page (served when the live day has not run)."""
    from .settings import ROOT

    (ROOT / "reports" / "story_replay.json").write_text(json.dumps(replay, ensure_ascii=False, indent=1, default=str))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--soak", type=int, default=0)
    a = ap.parse_args()
    db.init_db()
    with db.session() as s:
        if s.query(db.Farmer).count() == 0:
            from .seed import seed
            seed()
    if not a.soak:
        out = run_once(verbose=True)
        _p("Checks", json.dumps(out["checks"], indent=1))
        _write_replay(out["replay"])
        return
    sigs, fails = [], 0
    t0 = time.time()
    for i in range(a.soak):
        out = run_once(verbose=False)
        ok = all(out["checks"].values())
        fails += not ok
        sigs.append(out["signature"])
        if i == 0:
            _write_replay(out["replay"])
        print(f"run {i + 1:2d}: {'PASS' if ok else 'FAIL'} sig={out['signature']} changes={out['changes']} "
              f"callbacks={out['callbacks']} receipts={out['receipts_today']} ramesh_m3={out['ramesh_m3']}"
              + ("" if ok else f" {out['checks']}"), flush=True)
    same = len(set(sigs)) == 1
    print(f"\nsoak: {a.soak - fails}/{a.soak} passed, deterministic={same}, {time.time() - t0:.0f} s")
    if fails or not same:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
