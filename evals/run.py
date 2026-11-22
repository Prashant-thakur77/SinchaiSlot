"""`make evals`: agent eval suite, ASR robustness, optimiser benchmark, forecast backtest summary.

Writes reports/evals.json (read by the UI and README). Thresholds were fixed before the first run:
  case success >= 0.85, booking success >= 0.90, wrong-booking rate == 0.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp(prefix='sinchai-eval-')}/eval.db")
os.environ["LLM_PROVIDER"] = os.environ.get("EVAL_LLM_PROVIDER", "rules")

THRESHOLDS = {"case_success": 0.85, "booking_success": 0.90, "wrong_booking_rate": 0.0}


def _bookings(db, farmer_id=None):
    with db.session() as s:
        q = s.query(db.Booking)
        if farmer_id:
            q = q.filter(db.Booking.farmer_id == farmer_id)
        return {b.id: (b.status, b.m3_requested, b.farmer_id, b.plot_id) for b in q.all()}


def run_agent_eval(cases: list[dict], asr=None) -> dict:
    from sinchai_api import db, state
    from sinchai_api.agents import nlu, runtime, saathi
    from sinchai_api.seed import restore_snapshot

    results, latencies = [], []
    turns_tool = turns_tool_ok = 0
    should_not_book = wrong_bookings = 0
    booking_turns = booking_ok = 0
    lang_turns = lang_ok = 0
    wers = []
    for case in cases:
        restore_snapshot()
        runtime.SESSIONS.clear()
        state.reset_state()
        sid = f"eval-{case['id']}"
        fid = case["farmer"]
        failures = []
        for k, turn in enumerate(case["turns"]):
            said = turn["say"]
            if asr is not None and said:
                said = asr.transcribe(said, case["lang"])["text"]
                from sinchai_speech.adapters import wer
                wers.append(wer(turn["say"], said))
            before_all = _bookings(db)
            before = {b: v for b, v in before_all.items() if v[2] == fid}
            t0 = time.perf_counter()
            out = saathi.handle(sid, fid, said, channel="eval", opening=bool(case.get("opening")) and k == 0)
            latencies.append((time.perf_counter() - t0) * 1000)
            after_all = _bookings(db)
            after = {b: v for b, v in after_all.items() if v[2] == fid}
            new = [b for b in after if b not in before]
            tools_called = [c["tool"] for c in out["tool_calls"]]
            if "expect_tool" in turn:
                turns_tool += 1
                if turn["expect_tool"] in tools_called:
                    turns_tool_ok += 1
                else:
                    failures.append(f"t{k}: expected {turn['expect_tool']}, called {tools_called} (intent {out['intent']})")
            if "expect_pending" in turn:
                got = (out.get("pending") or {}).get("tool")
                if got != turn["expect_pending"]:
                    failures.append(f"t{k}: expected pending {turn['expect_pending']}, got {got}")
            if turn.get("expect_no_booking"):
                should_not_book += 1
                if new:
                    wrong_bookings += 1
                    failures.append(f"t{k}: booking created when none was intended")
            if turn.get("expect_no_booking_for_other"):
                others = [b for b in after_all if b not in before_all and after_all[b][2] != fid]
                should_not_book += 1
                if others:
                    wrong_bookings += 1
                    failures.append(f"t{k}: booking created for another farmer")
            if turn.get("expect_booking"):
                booking_turns += 1
                if len(new) == 1:
                    booking_ok += 1
                else:
                    failures.append(f"t{k}: expected one new booking, got {len(new)}")
                if turn.get("expect_within_cap") and new:
                    with db.session() as s:
                        b = s.get(db.Booking, new[0])
                        p = s.get(db.Plot, b.plot_id)
                        if b.m3_requested > p.need_m3 + 0.1:
                            failures.append(f"t{k}: booked {b.m3_requested} m3 above crop need {p.need_m3}")
            if turn.get("expect_cancelled") and not any(v[0] == "cancelled" for v in after.values()):
                failures.append(f"t{k}: booking not cancelled")
            if turn.get("expect_escalation"):
                with db.session() as s:
                    r = s.get(db.AgentRun, out["run_id"])
                    if r.status != "escalated":
                        failures.append(f"t{k}: expected hand-over to Saur Mitra")
            if said and not case.get("opening"):
                lang_turns += 1
                got_lang = nlu.detect_language(out["reply"], "hi")
                exp = case["lang"]
                if got_lang == exp or (exp in ("hi", "mai", "bho") and got_lang in ("hi", "mai", "bho") and k > 0):
                    lang_ok += 1
        results.append({"id": case["id"], "kind": case["kind"], "ok": not failures, "failures": failures})
    by_kind: dict[str, list[bool]] = {}
    for r in results:
        by_kind.setdefault(r["kind"], []).append(r["ok"])
    out = {
        "cases": len(results),
        "case_success": round(sum(r["ok"] for r in results) / len(results), 4),
        "tool_call_accuracy": round(turns_tool_ok / max(turns_tool, 1), 4),
        "booking_success": round(booking_ok / max(booking_turns, 1), 4),
        "wrong_booking_rate": round(wrong_bookings / max(should_not_book, 1), 4),
        "wrong_bookings": wrong_bookings,
        "reply_language_match": round(lang_ok / max(lang_turns, 1), 4),
        "latency_ms_p50": round(statistics.median(latencies), 1),
        "latency_ms_p95": round(sorted(latencies)[int(0.95 * (len(latencies) - 1))], 1),
        "by_kind": {k: {"n": len(v), "success": round(sum(v) / len(v), 3)} for k, v in sorted(by_kind.items())},
        "failures": [r for r in results if not r["ok"]][:60],
    }
    if wers:
        out["asr_wer_mean"] = round(statistics.mean(wers), 4)
    return out


def optimiser_benchmark(sizes=(5, 10, 20, 40, 60), reps=4) -> dict:
    import numpy as np
    from sinchai_planner.optimizer import Loads, PlanInput, Request, scenarios_from_quantiles, solve

    rows = []
    for n in sizes:
        for rep in range(reps):
            rng = np.random.default_rng(1000 * n + rep)
            shape = np.clip(np.sin(np.linspace(0.05, np.pi - 0.05, 24)), 0, None)
            peak = rng.uniform(2.5, 4.4)
            scen = scenarios_from_quantiles(shape * peak * 0.7, shape * peak * 0.9, shape * peak)
            reqs = [Request(f"r{i}", f"h{i % max(n - 3, 1)}", float(rng.uniform(10, 90)), float(rng.uniform(1, 3)),
                            due_today=i < n // 4, tenant=bool(i % 3 == 0)) for i in range(n)]
            loads = Loads(mill_backlog_kg=120, mill_value_rs_per_kwh=43, chaff_hours=2, chaff_value_rs_per_kwh=27,
                          battery_kwh_demand=6, battery_value_rs_per_kwh=20)
            base = dict(slot_starts=[f"T{k}" for k in range(24)], slot_h=0.5, scenarios=scen, requests=reqs, loads=loads,
                        budget_remaining_m3=float(rng.uniform(100, 400)), operator_slots=list(range(2, 22)))
            prod = solve(PlanInput(**base, time_limit_s=8.0, mip_rel_gap=1e-3))
            ref = solve(PlanInput(**base, time_limit_s=120.0, mip_rel_gap=0.0))
            gap = abs(ref.objective - prod.objective) / max(abs(ref.objective), 1e-9)
            rows.append({"requests": n, "rep": rep, "solve_s": round(prod.solve_s, 3), "ref_solve_s": round(ref.solve_s, 3),
                         "status": prod.status, "ref_status": ref.status, "gap_vs_reference": round(gap, 6),
                         "binaries": prod.n_binaries, "constraints": prod.n_constraints})
    summary = {}
    for n in sizes:
        r = [x for x in rows if x["requests"] == n]
        summary[str(n)] = {"solve_s_median": round(statistics.median(x["solve_s"] for x in r), 3),
                           "solve_s_max": round(max(x["solve_s"] for x in r), 3),
                           "gap_max": round(max(x["gap_vs_reference"] for x in r), 6),
                           "binaries_median": int(statistics.median(x["binaries"] for x in r))}
    return {"setting": "24 half-hour slots, 3 solar scenarios, mill + chaff + battery; production: gap 0.1%, 8 s limit; "
                       "reference: gap 0, 120 s", "by_size": summary, "runs": rows}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test", choices=["dev", "test"])
    ap.add_argument("--skip-bench", action="store_true")
    a = ap.parse_args()

    from datetime import date

    from sinchai_api import db, seed
    from sinchai_speech.adapters import TextASR

    from evals.agents.cases import DEV, TEST

    db.reset_engine()
    seed.seed(ledger_from=date(2024, 2, 20), verbose=False)
    cases = TEST if a.split == "test" else DEV
    t0 = time.time()
    agent = run_agent_eval(cases)
    print(f"agent eval ({a.split}): {json.dumps({k: v for k, v in agent.items() if k not in ('failures', 'by_kind')})}")
    robust = []
    book_cases = [c for c in cases if c["kind"] in ("book_yes", "book_no", "price", "cancel")]
    for noise in (0.1, 0.2, 0.3):
        r = run_agent_eval(book_cases, asr=TextASR(noise=noise, seed=7))
        robust.append({"simulated_word_noise": noise, "wer": r.get("asr_wer_mean"), "case_success": r["case_success"],
                       "wrong_booking_rate": r["wrong_booking_rate"]})
        print(f"asr noise {noise}: {robust[-1]}")
    out = {
        "generated_by": "make evals (evals/run.py)",
        "split": a.split, "thresholds": THRESHOLDS,
        "agent": agent,
        "passes_thresholds": agent["case_success"] >= THRESHOLDS["case_success"]
        and agent["booking_success"] >= THRESHOLDS["booking_success"]
        and agent["wrong_booking_rate"] <= THRESHOLDS["wrong_booking_rate"],
        "asr_robustness": {"label": "SIMULATED ASR word errors (drop/truncate) on the test utterances; real Indic ASR "
                                    "WER not measured (no hosted ASR configured)", "points": robust},
        "provider": os.environ["LLM_PROVIDER"],
    }
    fm = ROOT / "reports" / "cache" / "forecast_metrics.json"
    if fm.exists():
        out["forecast_backtest"] = json.loads(fm.read_text())
    if not a.skip_bench:
        out["optimiser_benchmark"] = optimiser_benchmark()
        print("optimiser:", json.dumps(out["optimiser_benchmark"]["by_size"]))
    v1 = ROOT / "reports" / "evals_test_v1_heldout.json"
    if a.split == "test" and v1.exists():
        first = json.loads(v1.read_text())
        out["first_heldout_run"] = {
            "label": "First run on the held-out test set, before any fix. This is the strictly held-out result.",
            **{k: first["agent"][k] for k in ("cases", "case_success", "tool_call_accuracy", "booking_success",
                                               "wrong_booking_rate", "reply_language_match")},
            "passes_thresholds": first["passes_thresholds"],
        }
        out["agent_label"] = ("After two fixes made from the first run's failures (an offer reply such as "
                              "'ok book it' accepts the offer; bare 'जी' is a yes). The test set is no longer "
                              "strictly held-out for this run.")
        if a.skip_bench and "optimiser_benchmark" in first:
            out["optimiser_benchmark"] = first["optimiser_benchmark"]
    out["runtime_s"] = round(time.time() - t0, 1)
    name = "evals.json" if a.split == "test" else "evals_dev.json"
    (ROOT / "reports" / name).write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"wrote reports/{name}; passes thresholds: {out['passes_thresholds']}")


if __name__ == "__main__":
    main()
