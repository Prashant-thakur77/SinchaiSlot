"""`make publish`: render README.md, submission/form-notes.md and the deck from reports/proof.json and
reports/evals.json, so every published number is copied from the files `make proof` / `make evals`
wrote. Nothing here computes a result."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from sinchai_schemas import constants as C

ROOT = Path(__file__).resolve().parents[3]


def pct(x: float, d: int = 0) -> str:
    return f"{x * 100:.{d}f}%"


def spct(x: float, d: int = 0) -> str:
    return f"{'+' if x >= 0 else '−'}{abs(x) * 100:.{d}f}%"


def n(x: float, d: int = 0) -> str:
    return f"{x:,.{d}f}"


def band(b: dict, f=n, d: int = 0) -> str:
    return f"{f(b['p50'], d)} (P10 {f(b['p10'], d)} to P90 {f(b['p90'], d)})"


def load() -> tuple[dict, dict]:
    proof = json.loads((ROOT / "reports" / "proof.json").read_text())
    ev_path = ROOT / "reports" / "evals.json"
    ev = json.loads(ev_path.read_text()) if ev_path.exists() else {}
    return proof, ev


def numbers(p: dict, ev: dict) -> dict:
    pol, g, h = p["policies"], p["gains"], p["headline"]
    D, B, Cp = pol["D"], pol["B"], pol["C"]
    out = {
        "util_D": n(D["utilisation_kwh_per_kwp"]["p50"]),
        "util_D_band": band(D["utilisation_kwh_per_kwp"]),
        "util_B": n(B["utilisation_kwh_per_kwp"]["p50"]),
        "util_C": n(Cp["utilisation_kwh_per_kwp"]["p50"]),
        "util_A": n(pol["A"]["utilisation_kwh_per_kwp"]["p50"]),
        "gain_B": spct(g["utilisation_D_vs_B"]["p50"]),
        "gain_B_band": f"P10 {spct(g['utilisation_D_vs_B']['p10'])} to P90 {spct(g['utilisation_D_vs_B']['p90'])}",
        "gain_C": spct(g["utilisation_D_vs_C"]["p50"]),
        "gain_Cl": spct(g["utilisation_D_vs_Cloads"]["p50"], 1),
        "share_D": pct(D["solar_share_used"]["p50"]),
        "share_B": pct(B["solar_share_used"]["p50"]),
        "rsm3_D": f"₹{D['farmer_rs_per_m3_solar']['p50']:.2f}",
        "rsm3_B": f"₹{B['farmer_rs_per_m3_solar']['p50']:.2f}",
        "rsm3_C": f"₹{Cp['farmer_rs_per_m3_solar']['p50']:.2f}",
        "rsm3_diesel": f"₹{h['diesel_rs_per_m3']:.2f}",
        "rs_irrig_D": f"₹{n(D['farmer_rs_per_irrigation']['p50'])}",
        "rs_irrig_diesel": f"₹{n(D['farmer_rs_per_irrigation_diesel_only']['p50'])}",
        "tenant_D": pct(D["tenant_share_served_by_solar"]["p50"]),
        "tenant_B": pct(B["tenant_share_served_by_solar"]["p50"]),
        "gini_D": f"{D['gini_solar_share_by_household']['p50']:.2f}",
        "gini_B": f"{B['gini_solar_share_by_household']['p50']:.2f}",
        "diesel_D": n(D["diesel_l_avoided"]["p50"]),
        "diesel_B": n(B["diesel_l_avoided"]["p50"]),
        "co2_D": n(D["co2_kg_avoided"]["p50"]),
        "solar_m3_D": n(D["solar_m3"]["p50"]),
        "solar_m3_B": n(B["solar_m3"]["p50"]),
        "need_m3": n(D["need_m3"]["p50"]),
        "m3_acre_D": n(D["m3_per_acre"]["p50"]),
        "m3_acre_B": n(B["m3_per_acre"]["p50"]),
        "overapp_B": n(B["over_application_m3"]["p50"]),
        "wait_p95_D": n(D["wait_days_p95"]["p50"]),
        "budget_days": n(D["budget_bound_days"]["p50"]),
        "budget_cap": n(D["budget_cap_m3"]["p50"]) if "budget_cap_m3" in D else "",
        "budget_exceed_D": pct(pol["D"]["runs_exceeding_budget_share"]),
        "budget_exceed_B": pct(pol["B"]["runs_exceeding_budget_share"]),
        "rev_D": f"₹{n(D['revenue_rs']['p50'])}",
        "rev_B": f"₹{n(B['revenue_rs']['p50'])}",
        "rev_mill_D": f"₹{n(D['revenue_mill_rs']['p50'])}",
        "rev_batt_D": f"₹{n(D['revenue_battery_rs']['p50'])}",
        "owner_D": f"₹{n(D['owner_fpo_income_rs']['p50'])}",
        "owner_B": f"₹{n(B['owner_fpo_income_rs']['p50'])}",
        "mitra_D": f"₹{n(D['saur_mitra_rs_per_month']['p50'])}",
        "payback_D": f"{D['payback_years']['p50']:.1f}",
        "payback_B": f"{B['payback_years']['p50']:.1f}",
        "platform_D": f"₹{n(D['platform_rs_per_year']['p50'])}",
        "solve_p95": f"{D['solve_s_p95']['p50']:.2f}" if "solve_s_p95" in D else "",
        "runs": str(p["setup"]["runs_per_policy"]),
        "seeds": str(p["setup"]["seeds"]),
        "years": ", ".join(map(str, p["setup"]["years"])),
        "fc_skill_p": pct(p["forecast"]["skill_vs_persistence"]),
        "fc_skill_c": pct(p["forecast"]["skill_vs_climatology"]),
        "fc_pin": f"{p['forecast']['sinchaislot_meta']['pinball_w_m2']}",
        "fc_pin_p": f"{p['forecast']['persistence']['pinball_w_m2']}",
        "fc_pin_c": f"{p['forecast']['climatology']['pinball_w_m2']}",
        "fc_cov": pct(p["forecast"]["sinchaislot_meta"]["p10_p90_coverage"]),
        "fc_hours": n(p["forecast"]["n_test_hours"]),
        "neg_mon": spct(p["negative_results"].get("gain_vs_Cloads_monsoon", 0), 1),
        "neg_dry": spct(p["negative_results"].get("gain_vs_Cloads_dry", 0), 1),
        "neg_text": p["negative_results"].get("explanation", ""),
        "neg_list": "\n".join(f"- {x}" for x in p["negative_results"].get("statements", [])),
        "diesel_C": n(Cp["diesel_l_avoided"]["p50"]),
        "gini_Cl": f"{pol['C+loads']['gini_solar_share_by_household']['p50']:.2f}" if "C+loads" in pol else "",
        "budget_lost": n(p["negative_results"].get("budget_tradeoff", {}).get("solar_m3_lost_to_budget_p50", 0)),
        "budget_text": p["negative_results"].get("budget_tradeoff", {}).get("explanation", ""),
        "demo_day": p["demo_day"]["date"],
        "generated_at": p["generated_at"],
    }
    if "D-persistence" in pol:
        out["gain_fc"] = spct(g["utilisation_D_vs_Dpersistence"]["p50"], 1)
        out["gain_oracle"] = spct(g["utilisation_Doracle_vs_D"]["p50"], 1)
    if ev.get("agent"):
        a, f = ev["agent"], ev.get("first_heldout_run", ev["agent"])
        out.update({
            "ev_cases": str(f["cases"]), "ev_case": pct(f["case_success"], 1), "ev_book": pct(f["booking_success"], 1),
            "ev_wrong": pct(f["wrong_booking_rate"], 1), "ev_tool": pct(f["tool_call_accuracy"], 1),
            "ev_pass": "yes" if f.get("passes_thresholds") else "no",
            "ev2_case": pct(a["case_success"], 1), "ev2_book": pct(a["booking_success"], 1), "ev2_wrong": pct(a["wrong_booking_rate"], 1),
            "ev_lang": pct(a["reply_language_match"], 1), "ev_lat": f"{a['latency_ms_p50']:.0f}",
        })
    return out


def unverified() -> list[str]:
    reg = yaml.safe_load((ROOT / "docs/schneider/register_map.yaml").read_text())["registers"]
    regs = [r["mnemonic"] for r in reg if not r.get("verified")]
    flt = yaml.safe_load((ROOT / "docs/schneider/fault_codes.yaml").read_text())["faults"]
    fl = [f["mnemonic"] for f in flt if not f.get("verified")]
    return regs, fl


def render_readme(v: dict) -> str:
    regs, fl = unverified()
    assumptions = [k for k, c in C.all_constants().items() if c.kind == "assumption"]
    return f"""# SinchaiSlot

**Every shared solar pump in a Bihar village is a 5 kW power plant that sleeps most of the day.**
SinchaiSlot runs it as a village micro-utility: water first for the farmers who book it, then the flour
mill, chaff cutter and battery packs with the sun that is left, all inside the village's groundwater
budget. A Schneider Altivar Solar drive runs the pump and meters it; a forecast-driven optimiser plans
tomorrow's sun; a Hindi, Maithili and Bhojpuri voice agent lets a farmer book with a free missed call;
and every booking leaves a verified receipt of water, diesel and CO₂ avoided.

Schneider Electric Yuva Yodha Energy Tech Hackathon 2026 · Challenge 1: Sustainable Agriculture ·
Pilot geography: Samastipur district, Bihar.

![architecture](docs/architecture.png)

## The proof (from `reports/proof.json`, generated {v['generated_at']})
{v['runs']} simulated years per policy ({v['seeds']} synthetic villages × held-out weather years {v['years']}), real
NASA POWER sun and real archived forecasts. P50 with P10 to P90 across runs.

| Metric | SinchaiSlot (D) | Chakhaji-style first-come (B, primary baseline) | Oorja-style (C) |
|---|---|---|---|
| Solar kWh used per kWp per year | **{v['util_D_band']}** | {v['util_B']} | {v['util_C']} |
| Gain in solar used vs B | **{v['gain_B']}** ({v['gain_B_band']}) | | {v['gain_C']} vs C |
| Farmer price, solar water | **{v['rsm3_D']}/m³** | {v['rsm3_B']}/m³ | {v['rsm3_C']}/m³ (diesel {v['rsm3_diesel']}) |
| Share of tenant water need met by solar | **{v['tenant_D']}** | {v['tenant_B']} | |
| Fairness of access (Gini, lower is fairer) | **{v['gini_D']}** | {v['gini_B']} | |
| Diesel avoided per pump-year | **{v['diesel_D']} L** ({v['co2_D']} kg CO₂) | {v['diesel_B']} L | {v['diesel_C']} L (no cap) |
| Seasons over the groundwater cap | **{v['budget_exceed_D']} of runs** | {v['budget_exceed_B']} of runs | |
| Pump revenue per year | **{v['rev_D']}** (mill {v['rev_mill_D']}, battery packs {v['rev_batt_D']}) | {v['rev_B']} | |
| Saur Mitra income | **{v['mitra_D']}/month** | | |

Owner-only use of the pump (policy A, context): {v['util_A']} kWh/kWp/yr.

**Where the gain comes from, and where it does not (published on purpose).** Most of the gain over the
baseline comes from giving the pump's spare sun somewhere useful to go (mill, chaff cutter, battery packs). The
planner's own contribution is fairness of access and holding the groundwater cap, not extra sun:
{v['neg_list']}

**Forecast (held-out {v['years']}).** Pinball loss {v['fc_pin']} W/m² vs {v['fc_pin_p']} (persistence) and
{v['fc_pin_c']} (climatology): {v['fc_skill_p']} and {v['fc_skill_c']} skill; P10-P90 coverage {v['fc_cov']} over
{v['fc_hours']} daylight hours.

**Agent (Saathi).** First run on {v.get('ev_cases', '–')} held-out scripted conversations: {v.get('ev_case', '–')} right,
{v.get('ev_book', '–')} of bookings completed, {v.get('ev_wrong', '–')} wrong bookings (met pre-set thresholds: {v.get('ev_pass', '–')}).
After two fixes from that run (test set no longer strictly held-out): {v.get('ev2_case', '–')}, {v.get('ev2_book', '–')},
{v.get('ev2_wrong', '–')}. Median reply {v.get('ev_lat', '–')} ms offline. Real Indic ASR word error rate is not measured (no
hosted speech service configured); a simulated ASR-noise sweep is in `reports/evals.json`.

## Quickstart (no paid keys)
```bash
docker compose up --build          # web :3000, api :8000, Modbus drive simulator :5020, MQTT :1883
make seed                           # demo database (also done automatically on first start)
make demo                           # the scripted day in the terminal
make soak                           # the 13:40 cloud scenario 10 times, checked for identical results
make proof                          # regenerate reports/proof.json and figures (about 20-30 min)
make evals                          # agent evals, ASR robustness, optimiser benchmark
make test                           # Python tests + Playwright end-to-end and accessibility
```
Without Docker: `uv sync -p 3.12`, `make api`, and in `apps/web`: `pnpm install && pnpm dev`.

Demo: open http://localhost:3000, press **Run 2 March live** or **Jump to 13:45**. Screens: Village
Twin, Planner, Saathi phone (missed call → Maithili callback → press 1), Altivar drive (inject a fault,
follow the Copilot), Rasid ledger (verify the chain, build a claim pack), Prayogshala (all numbers),
Agent trace, Hisaab, Pump cluster (three pumps on a Sentinel-2 image, data health, move an overflow booking to a
neighbour), Pump Passport (`/passport/P1`, one-page PDF), Saur Mitra app (`/mitra`: soil card, pay after harvest).

## What is in the box
| Module | What it does | Where |
|---|---|---|
| Surya Planner | Quantile solar forecast (3 NWP sources + meta-model), FAO-56 demand, two-stage stochastic MILP, re-planner with reasons | `services/planner` |
| Jal Prahari | Seasonal groundwater budget (hard), AWD, dry-run cut-off | `services/jalprahari`, `services/edge` |
| Rasid / Anudan Meter | Receipts, hash chain, Merkle proofs, anomaly audit, funder PDF, claim packs | `services/rasid` |
| Schneider drive | Register map from Altivar manuals, Modbus adapter, drive simulator, drive-as-meter | `services/devices`, `docs/schneider` |
| SinchaiSlot Edge | Offline plan, unlock codes, metering, cut-offs (Python + ESP32 firmware) | `services/edge` |
| Saathi, Copilot, Hisaab, Auditor | Agents over typed tools with confirmation gate and trace store; MCP server | `services/api` |
| Channels and speech | IVR callback, WhatsApp, USSD, ASR/TTS, all with local simulators | `services/channels`, `services/speech` |
| Paani Khata | Diesel and electric sellers as overflow agents | `services/api` |
| Prayogshala | Village twin, policies A-D, ablations, Monte Carlo, sensitivity | `services/sim` |
| Cluster | Three pumps on one forecast, booking transfer within channel reach, data-health monitor | `services/api/sinchai_api/cluster.py`, `services/edge` |
| Pump Passport | Utilisation, uptime, faults, receipts, repayment record, scorecard, PDF | `services/rasid` |
| Harvest-linked repayment | Part now, rest after harvest at the KCC rate; limit grows with on-time repayment | `services/rasid` |
| Soil and water | Soil Health Card reader (texture sets TAW), borewell water-quality card, recharge pairing | `services/planner`, `services/jalprahari` |
| Bharat-VISTAAR handoff | Agronomy questions go to the national advisory line with the farm context | `services/channels` |
| Pump Doctor | Dust, module, bearing and falling-water faults found from drive readings; misses and false alarms published | `services/devices/sinchai_devices/doctor.py`, `services/sim/sinchai_sim/doctor_eval.py` |
| Rollout calculator | 14 districts on real sun, site check for usable loads, who earns what | `services/data/sinchai_data/scale.py`, `apps/web/src/lib/economics.ts` |
| Sentinel-2 crop map | NDVI phenology classes and a true-colour basemap from 30 clear scenes | `services/data` |
| Web | Story page, dashboards, phone simulator, Saur Mitra PWA | `apps/web` |

More: `docs/architecture.md`, `docs/agents.md`, `docs/optimiser.md`, `docs/data.md`, `docs/edge-protocol.md`,
`docs/decisions/`.

## Data labels
Weather and forecasts: **REAL** (NASA POWER 2016-2025; Open-Meteo archived ECMWF IFS, GFS, ICON 2022-2025).
Satellite: **REAL** Sentinel-2 L2A imagery (Jun 2024-May 2025); crop-season classes **DERIVED**, not validated
against field labels.
Village, bookings, pump and drive telemetry, ledger history: **SIMULATED**. Prices, factors, capex,
subsidy rules: **PUBLISHED** with source URLs in `packages/schemas/sinchai_schemas/constants.yaml`.
Modelling values not found in a publication are marked **ASSUMPTION** there ({len(assumptions)} of them) and the
ones that move the headline are swept in the sensitivity analysis.

## UNVERIFIED (check before field use)
- Altivar registers with no published Modbus address: {', '.join(regs)}. They are never read over Modbus.
- Fault codes without a confirmed numeric value: {', '.join(fl) or 'none'}.
- Schneider brand green value (`--se: #3DCD58`) used in the UI.
- Samastipur pilot block CGWB category (assumed Safe) and the 450 mm annual extraction cap.
- Maithili and Bhojpuri phrasing (native-speaker review pending, docs/decisions/0005).
- Real Indic ASR accuracy (no hosted speech service configured).
- Bharat-VISTAAR integration API (no public API found; the HTTP adapter is a placeholder shape).
- Recharge shaft yield and cost (CGWB planning norm from a Rajasthan block plan, not Bihar).
- Site coordinates: the configured point is Samastipur town; re-run the crop map on the pilot cluster.
"""


def render_form_notes(v: dict) -> str:
    return f"""# Phase 2 form: facts, numbers and links per field

Facts only. Final answers are written by the team. Every number below is copied from
`reports/proof.json` (generated {v['generated_at']}) or `reports/evals.json`.

## Prototype stage
- Working software prototype; 365-day simulation per policy on real Samastipur weather.
- Field hardware simulated: Altivar Solar ATV320 behaviour model over the verified register map; Modbus TCP
  simulator; ESP32 edge firmware builds (not yet run on hardware).
- Runs with no paid keys: `docker compose up`.

## What it does (one line + modules)
- Shared solar pump as a village micro-utility: water first, then mill / chaff cutter / battery packs, inside a
  groundwater budget; missed-call booking in Maithili/Hindi/Bhojpuri; verified receipts.
- Modules: Saathi, Surya Planner, Saur Mitra Copilot, Jal Prahari, Rasid, Paani Khata, Anudan Meter, Hisaab,
  Prayogshala.
- Pump Doctor (slow faults from drive readings; `reports/doctor.json`), rollout calculator for 14 districts
  (`reports/scale.json`, screen /rollout), browser voice on the Saathi phone, evaluator page /judge.
- Extras: multi-pump cluster with booking transfer, Pump Passport (scorecard, PDF), data-health monitor,
  harvest-linked repayment, Soil Health Card reader, borewell water-quality card, recharge pairing,
  Bharat-VISTAAR handoff, Sentinel-2 crop-season map.

## Architecture
- Diagram: `docs/architecture.png` / `docs/architecture.svg`; description `docs/architecture.md`.
- EcoStruxure mapping: connected product (Altivar Solar drive) → edge control (SinchaiSlot Edge) → apps.

## Technologies / third-party services
- Python 3.12, FastAPI, Pydantic, SQLAlchemy, Postgres 16 + TimescaleDB + PostGIS, Redis, Mosquitto MQTT.
- HiGHS (MILP), LightGBM, pvlib, rasterio (Sentinel-2 COG reads), scikit-learn (Isolation Forest, TF-IDF), pymodbus, paho-mqtt, ReportLab.
- Next.js 16, React 19, Tailwind 4, GSAP, Lenis, Motion, d3; Playwright + axe.
- ESP32 (PlatformIO, Arduino): ModbusMaster, PubSubClient, ArduinoJson, mbedTLS HMAC.
- Data APIs: NASA POWER, Open-Meteo historical forecast API, Earth Search STAC (Sentinel-2 L2A on AWS). Optional adapters: hosted LLM, hosted Indic speech,
  WhatsApp Cloud API, IVR provider, UPI deep links (test mode).

## Data (real / sample / simulated)
- See `docs/data.md` (table with labels).

## Problem, with numbers (cited)
- Solar pumps use about {pct(C.get('ceew_solar_pump_utilisation'))} of their energy (CEEW, 1,131 pumps): {C.entry('ceew_solar_pump_utilisation').source_url}
- {pct(C.get('bihar_diesel_structures_share'))} of Bihar's groundwater structures run on diesel (IWMI): {C.entry('bihar_diesel_structures_share').source_url}
- {pct(C.get('bihar_farmers_buying_irrigation'), 1)} of farmers buy irrigation services (India Forum): {C.entry('bihar_farmers_buying_irrigation').source_url}
- Diesel water ₹{C.get('diesel_water_rs_per_hour')}/h vs solar ₹{C.get('solar_water_rs_per_hour')}/h in Chakhaji, Samastipur: {C.entry('diesel_water_rs_per_hour').source_url}
- 5 HP diesel pump ≈ {C.get('diesel_l_per_hour_5hp')} L/h (ACIAR); {C.get('co2_kg_per_l_diesel')} kg CO₂/L (India GHG Program).
- India stage of groundwater extraction {pct(C.get('india_gw_extraction_stage'), 2)} (CGWB 2025).

## Results and how measured
- Simulation: policies A (owner-only), B (Chakhaji first-come, primary baseline), C (Oorja-style), D (SinchaiSlot)
  on the same FAO-56 demand trace; {v['runs']} runs per policy; held-out years {v['years']}.
- Utilisation D {v['util_D_band']} kWh/kWp/yr vs B {v['util_B']} ({v['gain_B']}; {v['gain_B_band']}).
- Farmer price for solar water {v['rsm3_D']}/m³ vs B {v['rsm3_B']}/m³, diesel {v['rsm3_diesel']}/m³.
- Tenants: {v['tenant_D']} of tenant need met by solar vs {v['tenant_B']}; Gini {v['gini_D']} vs {v['gini_B']}.
- Diesel avoided {v['diesel_D']} L/yr per pump; CO₂ {v['co2_D']} kg/yr.
- Groundwater: seasons over the cap in {v['budget_exceed_D']} of D runs vs {v['budget_exceed_B']} of B runs.
- Forecast skill {v['fc_skill_p']} vs persistence, {v['fc_skill_c']} vs climatology (pinball loss, held-out years).
- Agent: {v.get('ev_cases', '–')} held-out conversations, {v.get('ev_case', '–')} correct, {v.get('ev_wrong', '–')} wrong bookings (first run).
- Negative results (verbatim from proof.json):
{v['neg_list']}

## Key metric
- Solar kWh used per kWp per year vs the Chakhaji-style baseline: {v['util_D']} vs {v['util_B']} ({v['gain_B']}).
- Secondary: farmer ₹ per m³ of solar water {v['rsm3_D']} vs diesel {v['rsm3_diesel']}.

## Cost to build and to scale
- Unit capex for a 5 HP / 5 kWp shared unit ≈ ₹{n(C.get('unit_capex_rs'))} (IWMI) [published].
- Retrofit kit (Altivar Solar drive + edge controller + optional meter): vendor quote needed [not yet quoted].
- Software running cost per pump: measure in a deployment [not yet measured]; demo runs on one laptop.
- O&M assumption ₹{n(C.get('om_rs_per_year'))}/yr [assumption].

## Business model
- Water per m³ (farmer), secondary energy per kg / hour / pack (mill, cutter, battery users), platform fee or revenue
  share (operators), paid verification receipts (CSR, lenders, programmes), retrofit kit via financing.
- Simulated pump revenue {v['rev_D']}/yr; owner/FPO income {v['owner_D']}/yr; Saur Mitra {v['mitra_D']}/month;
  platform {v['platform_D']}/yr; payback {v['payback_D']} years (B: {v['payback_B']}).

## Next steps
- Pilot on existing shared pumps in Samastipur; Oorja-style operators and Schneider partners; state programmes;
  PM-KUSUM universal controller.
- Field: confirm UNVERIFIED items (README), native-speaker review of Maithili/Bhojpuri, real ASR test set.

## Broader impact
- Diesel and CO₂ avoided; tenant access and fairness; Saur Mitra (women SHG) income; groundwater cap held.

## Links
- Repository: (add) · Demo video: (add) · Deck: `submission/deck/deck.pdf`
"""


def main() -> None:
    p, ev = load()
    v = numbers(p, ev)
    (ROOT / "README.md").write_text(render_readme(v))
    (ROOT / "submission").mkdir(exist_ok=True)
    (ROOT / "submission" / "form-notes.md").write_text(render_form_notes(v))
    (ROOT / "submission" / "deck").mkdir(parents=True, exist_ok=True)
    (ROOT / "submission" / "deck" / "numbers.json").write_text(json.dumps(v, indent=2, ensure_ascii=False))
    tpl = ROOT / "submission" / "video" / "storyboard.template.md"
    if tpl.exists():
        import re

        story = json.loads((ROOT / "reports" / "proof.json").read_text())
        vv = {**v, "diesel_rate": str(C.get("diesel_water_rs_per_hour")),
              "ceew": pct(C.get("ceew_solar_pump_utilisation"))}
        try:
            import httpx

            off = httpx.get("http://localhost:8000/api/story", timeout=5).json().get("offer") or {}
            vv["ramesh_need"] = str(round(off.get("numbers", {}).get("need_m3", 0)))
        except Exception:
            vv["ramesh_need"] = "{ramesh_need: run the API and re-publish}"
        text = re.sub(r"\{(\w+)\}", lambda m: vv.get(m.group(1), m.group(0)), tpl.read_text())
        text = text.replace("are filled from", "were filled from").replace("(see\n`storyboard.md`)", "")
        (ROOT / "submission" / "video" / "storyboard.md").write_text(text)
        _ = story
    from .deck import build_deck
    build_deck(v, ROOT / "submission" / "deck")
    print("wrote README.md, submission/form-notes.md, submission/deck/")


if __name__ == "__main__":
    main()
