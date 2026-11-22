"""`make proof`: regenerate reports/proof.json and every figure from real data.

Steps
  1. Forecast backtest on held-out 2024-2025 (pinball loss vs persistence and climatology).
  2. Monte Carlo: N synthetic villages x 2 held-out weather years x policies A-D and ablations.
  3. Sensitivity sweep (mill demand, battery packs, diesel delivery, budget depth, forecast noise).
  4. Negative results (monsoon weeks; cost of holding the groundwater budget).
  5. Demo-day extract (a real held-out day where cloud cut the afternoon) for the UI.
Every number in README, deck, video and UI is copied from the files this script writes.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd

from . import data
from . import engine as E
from . import metrics as M
from . import policies as P
from .village import demand_trace, make_village

YEARS = (2024, 2025)
POLICY_KEYS = ["A", "B", "C", "C+loads", "D", "D-nobudget", "D-persistence", "D-oracle", "D-noisy"]


def make_policy(key: str, seed: int) -> tuple[E.Policy, bool]:
    return {
        "A": (P.OwnerOnly(), False),
        "B": (P.Chakhaji(), False),
        "C": (P.OorjaStyle(), False),
        "C+loads": (P.OorjaPlusLoads(), False),
        "D": (P.SinchaiSlot(), True),
        "D-nobudget": (P.SinchaiSlot(), False),
        "D-persistence": (P.SinchaiSlot("persistence"), True),
        "D-oracle": (P.SinchaiSlot("oracle"), True),
        "D-noisy": (P.SinchaiSlot("noisy", noise_sd=0.35, seed=seed), True),
    }[key]


_YD: dict[int, E.YearData] = {}


def _year_data(year: int) -> E.YearData:
    if year not in _YD:
        _YD[year] = E.build_year_data(data.pv_actual(), data.forecast_pv(), date(year, 1, 1), date(year, 12, 31))
    return _YD[year]


def run_one(task: dict) -> dict:
    seed, year, key = task["seed"], task["year"], task["policy"]
    cfg = E.Config()
    for k, v in task.get("cfg", {}).items():
        cfg = replace(cfg, **{k: v})
    vil = make_village(seed)
    reqs = demand_trace(vil, data.daily_weather(), date(year, 1, 1), date(year, 12, 31))
    pol, budget = make_policy(key, seed)
    if "noise_sd" in task:
        pol = P.SinchaiSlot("noisy", noise_sd=task["noise_sd"], seed=seed)
    budget_mm = task.get("budget_mm")
    t0 = time.perf_counter()
    if budget and budget_mm:
        state = _run_with_budget_depth(pol, vil, reqs, _year_data(year), cfg, budget_mm)
    else:
        state = E.run_year(pol, vil, reqs, _year_data(year), cfg, with_budget=budget)
    m = M.year_metrics(state, pol.name)
    m.update({"seed": seed, "year": year, "key": key, "runtime_s": round(time.perf_counter() - t0, 1)})
    m.update({f"cfg_{k}": v for k, v in task.get("cfg", {}).items()})
    if budget_mm is not None:
        m["cfg_budget_mm"] = budget_mm
    if "noise_sd" in task:
        m["cfg_noise_sd"] = task["noise_sd"]
    if task.get("weekly"):
        w = M.weekly_series(state)
        m["weekly"] = {
            "week": [d.strftime("%Y-%m-%d") for d in w.index],
            "pv_kwh": w["pv_kwh"].round(1).tolist(),
            "useful_kwh": w["useful_kwh"].round(1).tolist(),
            "pump_kwh": w["pump_kwh"].round(1).tolist(),
            "water_m3": w["water_m3"].round(1).tolist(),
        }
    return m


def _run_with_budget_depth(pol, vil, reqs, yd, cfg, depth_mm) -> E.State:
    from sinchai_devices.physics import default_pump
    from sinchai_jal.budget import WaterBudget

    st = E.State(cfg=cfg, pump=default_pump(), village=vil,
                 budget=WaterBudget.for_cluster(command_area_ha=vil.area_ha, depth_mm=depth_mm))
    by_day: dict = {}
    for r in reqs:
        by_day.setdefault(r.day, []).append(r)
    for di in yd.days:
        E.run_day(st, pol, di, by_day.get(di.day, []))
    for rid in list(st.pending):
        p = st.pending.pop(rid)
        p.diesel_m3 += p.remaining
        p.remaining = 0
        st.done.append(p)
    return st


def _pool_map(tasks: list[dict], workers: int) -> list[dict]:
    if workers <= 1:
        return [run_one(t) for t in tasks]
    # Heaviest tasks first for better packing.
    order = sorted(range(len(tasks)), key=lambda i: 0 if tasks[i]["policy"].startswith("D") else 1)
    with ProcessPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(run_one, [tasks[i] for i in order], chunksize=1))
    out: list[dict] = [None] * len(tasks)  # type: ignore[list-item]
    for i, r in zip(order, res, strict=True):
        out[i] = r
    return out


NUMERIC_KEYS = [
    "utilisation_kwh_per_kwp", "solar_share_used", "solar_m3", "diesel_m3", "over_application_m3",
    "diesel_l_avoided", "co2_kg_avoided", "farmer_rs_per_m3_solar", "farmer_rs_per_m3_all_sources",
    "farmer_rs_per_irrigation", "farmer_rs_per_irrigation_diesel_only", "wait_days_p95",
    "tenant_share_served_by_solar", "gini_solar_share_by_household", "m3_per_acre", "m3_per_kg_cereal",
    "solar_extraction_m3", "budget_bound_days", "revenue_rs", "revenue_water_rs", "revenue_mill_rs",
    "revenue_chaff_rs", "revenue_battery_rs", "owner_fpo_income_rs", "saur_mitra_rs_per_month",
    "platform_rs_per_year", "payback_years", "mill_kg", "battery_kwh", "chaff_kwh", "pump_kwh", "useful_kwh",
    "pv_available_kwh", "solar_share_of_need", "replans", "solve_s_p50", "solve_s_p95", "need_m3",
]


def bands(rows: list[dict]) -> dict:
    out = {}
    for k in NUMERIC_KEYS:
        v = np.array([r[k] for r in rows if r.get(k) is not None], dtype=float)
        if len(v):
            out[k] = {"p10": round(float(np.percentile(v, 10)), 4), "p50": round(float(np.percentile(v, 50)), 4),
                      "p90": round(float(np.percentile(v, 90)), 4), "n": int(len(v))}
    seasons = [s for r in rows for s in r.get("budget_exceeded_seasons", [])]
    out["runs_exceeding_budget_share"] = round(sum(1 for r in rows if r.get("budget_exceeded_seasons")) / len(rows), 3)
    out["budget_exceeded_season_counts"] = {s: seasons.count(s) for s in set(seasons)}
    return out


def paired_gain(rows: list[dict], a: str, b: str, key: str) -> dict:
    """Relative gain of policy a over b on the same (seed, year), with bands."""
    idx = {(r["seed"], r["year"], r["key"]): r for r in rows}
    g = []
    for (s, y, k), r in idx.items():
        if k == a and (s, y, b) in idx and idx[(s, y, b)][key]:
            g.append(r[key] / idx[(s, y, b)][key] - 1)
    g = np.array(g)
    return {"p10": round(float(np.percentile(g, 10)), 4), "p50": round(float(np.percentile(g, 50)), 4),
            "p90": round(float(np.percentile(g, 90)), 4), "n": int(len(g))}


def negative_results(main_rows: list[dict]) -> dict:
    """Where the router adds little: weekly utilisation of D vs C+loads and vs B, monsoon vs dry season."""
    wk = {r["key"]: r["weekly"] for r in main_rows if "weekly" in r}
    out = {}
    if {"D", "B", "C+loads"} <= wk.keys():
        df = pd.DataFrame({"week": pd.to_datetime(wk["D"]["week"]), "pv": wk["D"]["pv_kwh"],
                           "D": wk["D"]["useful_kwh"], "B": wk["B"]["useful_kwh"], "Cl": wk["C+loads"]["useful_kwh"],
                           "Dpump": wk["D"]["pump_kwh"]})
        mon = df["week"].dt.month.isin([7, 8, 9])
        def gain(col, mask):
            base = df.loc[mask, col].sum()
            return round(float(df.loc[mask, "D"].sum() / base - 1), 4) if base else None
        out["monsoon_weeks"] = "July-September"
        out["gain_vs_B_monsoon"] = gain("B", mon)
        out["gain_vs_B_dry"] = gain("B", ~mon)
        out["gain_vs_Cloads_monsoon"] = gain("Cl", mon)
        out["gain_vs_Cloads_dry"] = gain("Cl", ~mon)
        out["monsoon_pump_share_of_useful"] = round(float(df.loc[mon, "Dpump"].sum() / max(df.loc[mon, "D"].sum(), 1)), 4)
        out["monsoon_pv_share_of_year"] = round(float(df.loc[mon, "pv"].sum() / df["pv"].sum()), 4)
    return out


def sp(x: float, d: int = 1) -> str:
    return f"{'+' if x >= 0 else '-'}{abs(x) * 100:.{d}f}%"


def narrate(proof: dict, rows: list[dict]) -> None:
    """Write the result statements from the numbers (no claim is typed by hand)."""
    pol, neg = proof["policies"], proof["negative_results"]
    g = proof["gains"]
    if "D-nobudget" in pol and "C+loads" in pol:
        g["utilisation_Dnobudget_vs_Cloads"] = paired_gain(rows, "D-nobudget", "C+loads", "utilisation_kwh_per_kwp")
        g["diesel_D_vs_C"] = paired_gain(rows, "D", "C", "diesel_l_avoided")
    statements = []
    if "utilisation_D_vs_Cloads" in g:
        a = g["utilisation_D_vs_Cloads"]
        statements.append(
            f"Against the same mill, cutter and battery packs run greedily, SinchaiSlot with the groundwater cap uses "
            f"{sp(a['p50'])} solar energy (P10 {sp(a['p10'])} to P90 {sp(a['p90'])}): the planner does not add sun on its own; "
            f"the extra loads do. Its gains are elsewhere: Gini of access {pol['D']['gini_solar_share_by_household']['p50']:.2f} "
            f"vs {pol['C+loads']['gini_solar_share_by_household']['p50']:.2f}, and the cap held in "
            f"{(1 - pol['D']['runs_exceeding_budget_share']) * 100:.0f}% of runs vs "
            f"{(1 - pol['C+loads']['runs_exceeding_budget_share']) * 100:.0f}%.")
    if "utilisation_Dnobudget_vs_Cloads" in g:
        statements.append(f"Without the cap the planner uses {sp(g['utilisation_Dnobudget_vs_Cloads']['p50'])} solar energy "
                          f"vs greedy dispatch and meets {pol['D-nobudget']['tenant_share_served_by_solar']['p50'] * 100:.0f}% "
                          f"of tenant need.")
    if "gain_vs_Cloads_monsoon" in neg:
        statements.append(f"By season (one village, first held-out year): {sp(neg['gain_vs_Cloads_monsoon'])} vs greedy loads in "
                          f"monsoon weeks, {sp(neg['gain_vs_Cloads_dry'])} in the rest of the year, when water demand fills the "
                          f"pump and the cap holds water back.")
    if "budget_tradeoff" in neg and "diesel_D_vs_C" in g:
        statements.append(f"The cap holds back {neg['budget_tradeoff']['solar_m3_lost_to_budget_p50']:,.0f} m3 of solar water a "
                          f"year, so SinchaiSlot avoids {abs(g['diesel_D_vs_C']['p50']) * 100:.1f}% {'less' if g['diesel_D_vs_C']['p50'] < 0 else 'more'} diesel than the per-m3 "
                          f"operator model without a cap; that water goes to diesel sellers on the same aquifer unless they "
                          f"share the cluster budget.")
    if "utilisation_D_vs_Dpersistence" in g:
        statements.append(f"The solar forecast adds {sp(g['utilisation_D_vs_Dpersistence']['p50'])} over planning on yesterday's "
                          f"sun; a perfect forecast would add {sp(g['utilisation_Doracle_vs_D']['p50'])} more.")
    neg["statements"] = statements
    neg["explanation"] = statements[0] if statements else ""
    if "budget_tradeoff" in neg and len(statements) > 3:
        neg["budget_tradeoff"]["explanation"] = statements[3]


def demo_day() -> dict:
    """A real held-out day whose afternoon sun fell well below the P50 forecast."""
    pv = data.pv_actual()
    fc = data.forecast_pv()
    best, best_score = None, -1.0
    for d in pd.date_range("2024-01-15", "2024-03-31", freq="D"):
        idx = [pd.Timestamp(f"{d.date()} {h:02d}:30", tz="Asia/Kolkata") for h in E.SLOT_HOURS]
        a = pv.reindex(idx).fillna(0).to_numpy()
        f = fc.reindex(idx).fillna(0)
        morning_ok = a[3:7].mean() > 0.8 * f["q50"].to_numpy()[3:7].mean() and a[3:7].mean() > 2.0
        drop = f["q50"].to_numpy()[7:10].mean() - a[7:10].mean()
        if morning_ok and drop > best_score:
            best, best_score = (d, idx, a, f), drop
    d, idx, a, f = best
    return {
        "date": d.date().isoformat(),
        "label": "Held-out 2024 day, real NASA POWER sun vs SinchaiSlot P10/P50/P90 forecast",
        "slots": [i.strftime("%H:%M") for i in idx],
        "pv_actual_kw": [round(float(x), 3) for x in a],
        "pv_q10_kw": [round(float(x), 3) for x in f["q10"]],
        "pv_q50_kw": [round(float(x), 3) for x in f["q50"]],
        "pv_q90_kw": [round(float(x), 3) for x in f["q90"]],
        "afternoon_shortfall_kw": round(float(best_score), 3),
    }


def figures(proof: dict, out_dir) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False})
    files = []
    pol = proof["policies"]
    keys = ["A", "B", "C", "C+loads", "D"]
    labels = ["A Owner-only", "B Chakhaji", "C Oorja-style", "C + loads", "D SinchaiSlot"]
    colors = ["#9AA59F", "#C9A86A", "#7FA3B8", "#6C8C9E", "#F5B83D"]

    def bar(metric: str, title: str, fname: str, fmt="{:.0f}"):
        fig, ax = plt.subplots(figsize=(7, 3.6))
        ks = [k for k in keys if metric in pol[k]]  # e.g. owner-only sells no water, so it has no price
        lab = [labels[keys.index(k)] for k in ks]
        col = [colors[keys.index(k)] for k in ks]
        p50 = [pol[k][metric]["p50"] for k in ks]
        lo = [pol[k][metric]["p50"] - pol[k][metric]["p10"] for k in ks]
        hi = [pol[k][metric]["p90"] - pol[k][metric]["p50"] for k in ks]
        ax.bar(lab, p50, color=col, yerr=[lo, hi], capsize=4, ecolor="#333")
        for i, v in enumerate(p50):
            ax.text(i, v, fmt.format(v), ha="center", va="bottom", fontsize=9)
        ax.set_title(title, loc="left", fontsize=11)
        ax.tick_params(axis="x", labelsize=8.5)
        fig.tight_layout()
        for ext in ("png", "svg"):
            fig.savefig(out_dir / f"{fname}.{ext}", dpi=160)
        plt.close(fig)
        files.append(fname)

    bar("utilisation_kwh_per_kwp", "Solar kWh used per kWp per year (P50, bars P10-P90)", "utilisation")
    bar("tenant_share_served_by_solar", "Share of tenant water need met by solar", "tenants", "{:.2f}")
    bar("gini_solar_share_by_household", "Gini of solar share across households (lower is fairer)", "fairness", "{:.2f}")
    bar("farmer_rs_per_m3_solar", f"Farmer Rs per m3 of solar water (diesel = Rs {proof['headline']['diesel_rs_per_m3']:.1f})", "rs_per_m3", "{:.2f}")

    wk = proof.get("weekly_example", {})
    if wk:
        fig, ax = plt.subplots(figsize=(8, 3.4))
        weeks = pd.to_datetime(wk["D"]["week"])
        ax.fill_between(weeks, wk["D"]["pv_kwh"], color="#F5B83D", alpha=0.18, label="Solar available")
        for k, c in [("B", "#C9A86A"), ("C+loads", "#6C8C9E"), ("D", "#E39B12")]:
            ax.plot(weeks, wk[k]["useful_kwh"], color=c, lw=1.6, label=f"{k} used")
        ax.axvspan(pd.Timestamp(f"{weeks[0].year}-07-01"), pd.Timestamp(f"{weeks[0].year}-09-30"), color="#3BA7E5",
                   alpha=0.08, label="Monsoon (negative result)")
        ax.set_ylabel("kWh / week")
        ax.legend(fontsize=8, ncol=3, frameon=False)
        ax.set_title("Weekly solar used, one village, held-out year", loc="left", fontsize=11)
        fig.tight_layout()
        for ext in ("png", "svg"):
            fig.savefig(out_dir / f"weekly.{ext}", dpi=160)
        plt.close(fig)
        files.append("weekly")

    dd = proof["demo_day"]
    fig, ax = plt.subplots(figsize=(7, 3.2))
    x = np.arange(len(dd["slots"]))
    ax.fill_between(x, dd["pv_q10_kw"], dd["pv_q90_kw"], color="#F5B83D", alpha=0.25, label="P10-P90 forecast")
    ax.plot(x, dd["pv_q50_kw"], color="#E39B12", lw=1.6, label="P50 forecast")
    ax.plot(x, dd["pv_actual_kw"], color="#0E1512", lw=1.8, label="Actual")
    ax.set_xticks(x, dd["slots"], fontsize=8)
    ax.set_ylabel("PV kW")
    ax.legend(fontsize=8, frameon=False)
    ax.set_title(f"Demo day {dd['date']}: forecast band vs actual sun", loc="left", fontsize=11)
    fig.tight_layout()
    for ext in ("png", "svg"):
        fig.savefig(out_dir / f"demo_day.{ext}", dpi=160)
    plt.close(fig)
    files.append("demo_day")

    sens = proof.get("sensitivity", {})
    if sens:
        rows = []
        for name, pts in sens.items():
            vals = [p["utilisation_kwh_per_kwp"] for p in pts]
            rows.append((name, min(vals), max(vals)))
        base = pol["D"]["utilisation_kwh_per_kwp"]["p50"]
        fig, ax = plt.subplots(figsize=(7, 3.2))
        for i, (_n, lo, hi) in enumerate(rows):
            ax.barh(i, hi - lo, left=lo, color="#3BA7E5", alpha=0.7)
        ax.axvline(base, color="#E39B12", lw=1.2)
        ax.set_yticks(range(len(rows)), [r[0] for r in rows], fontsize=8)
        ax.set_xlabel("D utilisation, kWh/kWp/yr")
        ax.set_title("Sensitivity of the headline to assumptions", loc="left", fontsize=11)
        fig.tight_layout()
        for ext in ("png", "svg"):
            fig.savefig(out_dir / f"sensitivity.{ext}", dpi=160)
        plt.close(fig)
        files.append("sensitivity")
    return files


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--sens-seeds", type=int, default=3)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--refit-forecast", action="store_true")
    ap.add_argument("--quick", action="store_true", help="2 seeds, 1 year, small sweep (CI smoke)")
    ap.add_argument("--figures-only", action="store_true", help="redraw figures from the existing proof.json")
    a = ap.parse_args()
    if a.figures_only:
        proof = json.loads((data.REPORTS / "proof.json").read_text())
        rows = [r for r in json.loads((data.REPORTS / "runs.json").read_text()) if "sweep" not in r and r.get("seed", 0) < 100]
        narrate(proof, rows)
        (data.REPORTS / "proof.json").write_text(json.dumps(proof, indent=2, default=str))
        print(figures(proof, data.REPORTS / "figures"))
        return
    t0 = time.time()
    preds, fc_metrics = data.ensure_forecasts(refit=a.refit_forecast)
    years = YEARS[:1] if a.quick else YEARS
    seeds = 2 if a.quick else a.seeds
    keys = ["A", "B", "C", "C+loads", "D"] if a.quick else POLICY_KEYS

    tasks = [{"seed": s, "year": y, "policy": k, "weekly": s == 0} for s in range(seeds) for y in years for k in keys]
    sens_tasks = []
    ss = 1 if a.quick else a.sens_seeds
    sweep = {
        "mill_demand_kg_per_day": [{"cfg": {"mill_kg_per_day": v}} for v in (60, 120, 240)],
        "battery_packs_per_day": [{"cfg": {"packs_per_day": v}} for v in (0, 6, 12)],
        "budget_depth_mm": [{"budget_mm": v} for v in (300, 450, 700)],
        "forecast_noise_sd": [{"noise_sd": v} for v in (0.2, 0.4, 0.6)],
    }
    if not a.quick:
        sweep["diesel_flow_m3h"] = [{"cfg": {"diesel_flow_m3h": v}} for v in (20, 30)]
    for name, pts in sweep.items():
        for j, pt in enumerate(pts):
            for s in range(ss):
                for k in (["D", "B"] if name == "diesel_flow_m3h" else ["D"]):
                    sens_tasks.append({"seed": 100 + s, "year": 2024, "policy": k, "sweep": name, "point": j, **pt})

    print(f"running {len(tasks)} main + {len(sens_tasks)} sensitivity simulations on {a.workers} workers")
    res = _pool_map(tasks + sens_tasks, a.workers)
    main_rows = res[: len(tasks)]
    sens_rows = res[len(tasks):]

    by_key: dict[str, list[dict]] = {}
    for r in main_rows:
        by_key.setdefault(r["key"], []).append(r)
    policies = {k: bands(v) for k, v in by_key.items()}

    sensitivity: dict[str, list[dict]] = {}
    for t, r in zip(sens_tasks, sens_rows, strict=True):
        if r["key"] != "D":
            continue
        sensitivity.setdefault(t["sweep"], [])
    for name, pts in sweep.items():
        for j, pt in enumerate(pts):
            rows = [r for t, r in zip(sens_tasks, sens_rows, strict=True)
                    if t["sweep"] == name and t["point"] == j and r["key"] == "D"]
            brow = [r for t, r in zip(sens_tasks, sens_rows, strict=True)
                    if t["sweep"] == name and t["point"] == j and r["key"] == "B"]
            val = pt.get("cfg", {}) or {k: v for k, v in pt.items() if k in ("budget_mm", "noise_sd")}
            entry = {"setting": val,
                     "utilisation_kwh_per_kwp": round(float(np.median([r["utilisation_kwh_per_kwp"] for r in rows])), 1),
                     "solar_m3": round(float(np.median([r["solar_m3"] for r in rows])), 0),
                     "farmer_rs_per_m3_solar": round(float(np.median([r["farmer_rs_per_m3_solar"] for r in rows])), 3),
                     "owner_fpo_income_rs": round(float(np.median([r["owner_fpo_income_rs"] for r in rows])), 0),
                     "budget_bound_days": round(float(np.median([r["budget_bound_days"] for r in rows])), 0)}
            if brow:
                entry["B_farmer_rs_per_m3_solar"] = round(float(np.median([r["farmer_rs_per_m3_solar"] for r in brow])), 3)
                entry["diesel_rs_per_m3"] = round(float(np.median([r["diesel_rs_per_m3"] for r in brow])), 3)
            sensitivity.setdefault(name, []).append(entry)

    gains = {
        "utilisation_D_vs_B": paired_gain(main_rows, "D", "B", "utilisation_kwh_per_kwp"),
        "utilisation_D_vs_C": paired_gain(main_rows, "D", "C", "utilisation_kwh_per_kwp"),
        "utilisation_D_vs_Cloads": paired_gain(main_rows, "D", "C+loads", "utilisation_kwh_per_kwp"),
        "tenant_share_D_vs_B": paired_gain(main_rows, "D", "B", "tenant_share_served_by_solar"),
        "rs_per_m3_solar_D_vs_B": paired_gain(main_rows, "D", "B", "farmer_rs_per_m3_solar"),
        "revenue_D_vs_B": paired_gain(main_rows, "D", "B", "revenue_rs"),
    }
    if "D-persistence" in by_key:
        gains["utilisation_D_vs_Dpersistence"] = paired_gain(main_rows, "D", "D-persistence", "utilisation_kwh_per_kwp")
        gains["utilisation_Doracle_vs_D"] = paired_gain(main_rows, "D-oracle", "D", "utilisation_kwh_per_kwp")
        gains["solar_m3_Dnobudget_vs_D"] = paired_gain(main_rows, "D-nobudget", "D", "solar_m3")

    weekly_example = {r["key"]: r["weekly"] for r in main_rows if "weekly" in r and r["year"] == years[0]}
    neg = negative_results([r for r in main_rows if r["seed"] == 0 and r["year"] == years[0]])
    if "D-nobudget" in by_key:
        neg["budget_tradeoff"] = {
            "solar_m3_lost_to_budget_p50": round(
                policies["D-nobudget"]["solar_m3"]["p50"] - policies["D"]["solar_m3"]["p50"], 0),
        }

    proof = {
        "generated_by": "make proof (services/sim/sinchai_sim/proof.py)",
        "generated_at": pd.Timestamp.now(tz="Asia/Kolkata").isoformat(timespec="seconds"),
        "runtime_s": None,
        "labels": {
            "weather": "REAL: NASA POWER hourly, Samastipur, 2016-2025",
            "forecasts": "REAL: Open-Meteo historical forecasts (ECMWF IFS, GFS, ICON), 2022-2025",
            "village_and_bookings": "SIMULATED: synthetic village calibrated to Bihar holdings",
            "pump_and_drive": "SIMULATED: physics model of a 5 HP pump on an Altivar Solar drive",
            "prices_and_factors": "PUBLISHED and ASSUMPTION values from constants.yaml",
        },
        "setup": {"seeds": seeds, "years": list(years), "households": 50, "pv_kwp": 5,
                  "runs_per_policy": seeds * len(years), "policies": keys},
        "forecast": fc_metrics,
        "policies": policies,
        "gains": gains,
        "sensitivity": sensitivity,
        "negative_results": neg,
        "demo_day": demo_day(),
        "weekly_example": weekly_example,
    }
    proof["headline"] = {
        "utilisation_D_kwh_per_kwp": policies["D"]["utilisation_kwh_per_kwp"]["p50"],
        "utilisation_B_kwh_per_kwp": policies["B"]["utilisation_kwh_per_kwp"]["p50"],
        "utilisation_gain_vs_B": gains["utilisation_D_vs_B"]["p50"],
        "utilisation_gain_vs_C": gains["utilisation_D_vs_C"]["p50"],
        "farmer_rs_per_m3_D": policies["D"]["farmer_rs_per_m3_solar"]["p50"],
        "farmer_rs_per_m3_B": policies["B"]["farmer_rs_per_m3_solar"]["p50"],
        "diesel_rs_per_m3": E.Config().diesel_rs_per_m3,
        "diesel_l_avoided_D": policies["D"]["diesel_l_avoided"]["p50"],
        "co2_kg_avoided_D": policies["D"]["co2_kg_avoided"]["p50"],
        "tenant_share_D": policies["D"]["tenant_share_served_by_solar"]["p50"],
        "tenant_share_B": policies["B"]["tenant_share_served_by_solar"]["p50"],
        "gini_D": policies["D"]["gini_solar_share_by_household"]["p50"],
        "gini_B": policies["B"]["gini_solar_share_by_household"]["p50"],
        "budget_exceeded_D_runs_share": policies["D"]["runs_exceeding_budget_share"],
        "forecast_skill_vs_persistence": fc_metrics["skill_vs_persistence"],
        "forecast_skill_vs_climatology": fc_metrics["skill_vs_climatology"],
    }
    narrate(proof, main_rows)
    proof["runtime_s"] = round(time.time() - t0, 1)
    out = data.REPORTS / ("proof_quick.json" if a.quick else "proof.json")
    out.write_text(json.dumps(proof, indent=2, default=str))
    (data.REPORTS / "runs.json").write_text(json.dumps(
        [{k: v for k, v in r.items() if k != "weekly"} for r in main_rows + sens_rows], default=str))
    if not a.quick:
        figures(proof, data.REPORTS / "figures")
    print(json.dumps(proof["headline"], indent=2))
    print(f"wrote {out} in {proof['runtime_s']} s")


if __name__ == "__main__":
    main()
