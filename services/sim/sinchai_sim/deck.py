"""15-slide deck (HTML, 1920x1080) rendered from proof numbers; `node apps/web/.deckpdf.mjs` prints it to PDF."""

from __future__ import annotations

from pathlib import Path

from sinchai_schemas import constants as C

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@500;700;800&family=Geist:wght@400;500&family=Geist+Mono:wght@400;500&family=Noto+Sans+Devanagari:wght@400;600&display=swap');
:root{--night:#0E1512;--night2:#142019;--soil:#2A3A30;--mist:#9FB0A6;--fog:#C9D3CD;--sun:#F5B83D;--water:#3BA7E5;--leaf:#5BBF6A;--se:#3DCD58;--paper:#F3EEE2;--ink:#13201A}
*{box-sizing:border-box;margin:0}
@page{size:1920px 1080px;margin:0}
body{background:#000;font-family:Geist,system-ui,sans-serif;color:#eef3ee}
.s{width:1920px;height:1080px;padding:96px 120px;background:var(--night);position:relative;overflow:hidden;page-break-after:always;display:flex;flex-direction:column}
.s.gold{background:var(--sun);color:var(--ink)} .s.paper{background:var(--paper);color:var(--ink)}
h1{font-family:'Bricolage Grotesque';font-weight:800;font-size:150px;letter-spacing:-.02em;line-height:.9;color:var(--sun)}
h2{font-family:'Bricolage Grotesque';font-weight:700;font-size:72px;letter-spacing:-.015em;line-height:1.02;max-width:1500px}
.kick{font-family:'Geist Mono';font-size:24px;color:var(--sun);margin-bottom:28px} .gold .kick,.paper .kick{color:var(--ink);opacity:.7}
p,li{font-size:30px;line-height:1.45;color:var(--fog)} .gold p,.paper p,.gold li,.paper li{color:var(--ink)}
.num{font-family:'Geist Mono';font-variant-numeric:tabular-nums}
.big{font-family:'Geist Mono';font-size:120px;line-height:1;color:var(--sun)} .gold .big{color:var(--ink)}
.grid{display:grid;gap:48px;margin-top:auto}
.g3{grid-template-columns:repeat(3,1fr)} .g2{grid-template-columns:1fr 1fr} .g4{grid-template-columns:repeat(4,1fr)}
.lab{font-size:24px;color:var(--mist);margin-top:14px} .gold .lab,.paper .lab{color:rgba(19,32,26,.7)}
.tag{display:inline-block;font-family:'Geist Mono';font-size:16px;border:1.5px solid currentColor;border-radius:99px;padding:2px 12px;margin-left:10px;vertical-align:middle}
table{border-collapse:collapse;width:100%;margin-top:40px;font-size:24px} td,th{padding:14px 16px;border-bottom:1px solid var(--soil);text-align:left;color:var(--fog);vertical-align:top} th{color:var(--mist);font-weight:500}
td.d{color:var(--sun);font-family:'Geist Mono'} .foot{position:absolute;bottom:40px;left:120px;right:120px;display:flex;justify-content:space-between;font-family:'Geist Mono';font-size:18px;color:var(--mist)}
.gold .foot,.paper .foot{color:rgba(19,32,26,.6)}
img.fig{width:100%;border-radius:12px;background:#fff;margin-top:32px}
.deva{font-family:'Noto Sans Devanagari'}
.wire{display:flex;gap:0;margin-top:60px} .wire div{flex:1;border-top:4px solid var(--se);padding:28px 40px 0 0} .wire div:nth-child(2){border-color:var(--sun)} .wire div:nth-child(3){border-color:var(--water)}
.wire b{display:block;font-family:'Bricolage Grotesque';font-size:40px;color:#fff;margin:8px 0 14px}
"""


def build_deck(v: dict, out_dir: Path) -> Path:
    src = lambda k: C.entry(k).source_url  # noqa: E731
    slides = []

    def s(body: str, cls: str = "", page: int = 0, note: str = "") -> None:
        slides.append(f'<section class="s {cls}">{body}<div class="foot"><span>SinchaiSlot · Yuva Yodha 2026 · Challenge 1</span><span>{note}</span><span>{page:02d}</span></div></section>')

    s(f"""<div class="kick">Samastipur, Bihar · shared solar irrigation</div>
<h1>SINCHAISLOT</h1>
<h2 style="margin-top:60px;color:#eef3ee">Water first, then everything else, inside the village's groundwater budget.</h2>
<p style="margin-top:40px;max-width:1450px">Ramesh books water with a missed call and pays per cubic metre; every sunny kWh his booking does not need goes to the mill or a battery, so the pump earns more, his water gets cheaper, and the village stays inside its groundwater budget.</p>""", page=1)

    s(f"""<div class="kick">The person</div><h2>Ramesh rents half an acre of wheat. Next door, a solar pump sits idle at noon while he pays a diesel seller.</h2>
<div class="grid g3"><div><div class="big">₹{C.get('diesel_water_rs_per_hour')}</div><div class="lab">per hour for diesel water in Chakhaji <span class="tag">PUBLISHED</span></div></div>
<div><div class="big">{round(C.get('bihar_farmers_buying_irrigation') * 100, 1)}%</div><div class="lab">of farmers buy irrigation as a service <span class="tag">PUBLISHED</span></div></div>
<div><div class="big">{C.get('bihar_avg_holding_ha')} ha</div><div class="lab">average holding in Bihar <span class="tag">PUBLISHED</span></div></div></div>""", page=2, note="Sources: India Forum, IWMI")

    s(f"""<div class="kick">Three wasted resources</div><h2>Idle sunshine. Diesel burned next door. Groundwater with no budget.</h2>
<div class="grid g3"><div><div class="big">{round(C.get('ceew_solar_pump_utilisation') * 100)}%</div><div class="lab">of solar pump energy used (1,131 pumps) <span class="tag">PUBLISHED</span></div></div>
<div><div class="big">{round(C.get('bihar_diesel_structures_share') * 100)}%</div><div class="lab">of Bihar's groundwater structures run on diesel <span class="tag">PUBLISHED</span></div></div>
<div><div class="big">{C.get('india_gw_extraction_stage') * 100:.1f}%</div><div class="lab">stage of groundwater extraction, India <span class="tag">PUBLISHED</span></div></div></div>""", page=3, note="Sources: CEEW, IWMI, CGWB 2025")

    s("""<div class="kick">What exists, and what is missing</div><h2>Sharing a solar pump is proven. The planning, verification and access layer is not built.</h2>
<table><tr><th>Existing model (from the team's research)</th><th>What it lacks</th></tr>
<tr><td>Hourly solar water sales in Samastipur (Chakhaji)</td><td>Informal, phone-call based, no queue, no metering, no budget</td></tr>
<tr><td>Pay-per-use solar irrigation at Rs 3-4 per m³ with a mill</td><td>Rule-based scheduling, fixed tariff, no planning, no farmer voice channel, mill runs first-come</td></tr>
<tr><td>Booking shared solar kits by the hour</td><td>No forecast, no secondary loads, no water budget, no verification</td></tr>
<tr><td>Women-SHG solar enterprises, 5 HP / 5 kWp, about 20 acres</td><td>No digital layer</td></tr>
<tr><td>EcoStruxure-managed village solar with load diversion (one site)</td><td>Single site, rule-based</td></tr></table>
<p style="margin-top:28px;font-size:22px;color:var(--mist)">Team to review this slide's wording before submission.</p>""", page=4)

    s("""<div class="kick">SinchaiSlot in one picture</div><h2 style="font-size:60px">One pump, three jobs, in order.</h2>
<img class="fig" src="../../docs/architecture.png" style="background:none;max-height:700px;object-fit:contain">""", page=5)

    s(f"""<div class="kick">The hero mechanism</div><h2>Forecast the sun. Fill it with water first. Route what is left. Never cross the budget.</h2>
<img class="fig" src="../../reports/figures/demo_day.png" style="max-height:440px;object-fit:contain">
<p style="margin-top:24px">Real held-out day {v['demo_day']}: at 13:40 the actual sun fell below the P10 forecast; the planner re-flowed the afternoon, froze the next hour, and Saathi called each moved farmer in their language.</p>""", page=6, note="REAL sun · SIMULATED village")

    s(f"""<div class="kick">Agents and channels</div><h2>A free missed call. A callback in Maithili. Nothing booked until he says yes.</h2>
<div class="grid g2"><div><p class="deva" style="font-size:34px;color:#fff">“हँ, बुक करू”</p><p>Saathi sizes the booking to the crop (FAO-56), quotes per m³ under diesel, reads it back, and books only on a clear yes. IVR, WhatsApp, USSD, Saur Mitra-assisted.</p></div>
<div><div class="big">{v.get('ev_wrong', '–')}</div><div class="lab">wrong bookings on {v.get('ev_cases', '–')} held-out conversations ({v.get('ev_case', '–')} fully right, first run)</div>
<p style="margin-top:24px;font-size:24px">Agents plan, explain and talk; a deterministic optimiser and the edge controller execute. Every tool call is typed, logged and replayable; MCP server included.</p></div></div>""", page=7)

    s("""<div class="kick">Schneider inside</div><h2>Remove the Altivar Solar drive and nothing works.</h2>
<div class="wire"><div><span class="kick" style="color:var(--se)">Connected product</span><b>Altivar Solar ATV320</b><p style="font-size:24px">Actuator: CMD 8501, LFR 8502. Meter: RFR 3202, OPR 3211, APH 3230. Faults: LFT 7121 drive the Copilot. Registers taken only from the Altivar manuals.</p></div>
<div><span class="kick">Edge control</span><b>SinchaiSlot Edge</b><p style="font-size:24px">ESP32 or Linux beside the drive. Holds tomorrow's plan offline, unlock codes, drive-as-meter, budget and dry-run cut-off.</p></div>
<div><span class="kick" style="color:var(--water)">Apps and analytics</span><b>Planner · Saathi · Rasid</b><p style="font-size:24px">Forecast and stochastic MILP, voice agent, verified receipts, groundwater guard, funder ledger.</p></div></div>""", page=8)

    s("""<div class="kick">Architecture</div><img class="fig" src="../../docs/architecture.png" style="background:none;max-height:860px;object-fit:contain;margin-top:0">""", page=9)

    s(f"""<div class="kick">Proof · {v['runs']} simulated years per policy · held-out weather {v['years']}</div><h2>{v['util_D']} kWh of sun used per kWp per year, against {v['util_B']} for first-come hourly sales.</h2>
<div class="grid g4"><div><div class="big" style="font-size:96px">{v['gain_B']}</div><div class="lab">solar used vs baseline ({v['gain_B_band']})</div></div>
<div><div class="big" style="font-size:96px">{v['rsm3_D']}</div><div class="lab">farmer per m³ (baseline {v['rsm3_B']}, diesel {v['rsm3_diesel']})</div></div>
<div><div class="big" style="font-size:96px">{v['diesel_D']} L</div><div class="lab">diesel avoided per pump-year ({v['co2_D']} kg CO₂)</div></div>
<div><div class="big" style="font-size:96px">{v['fc_skill_p']}</div><div class="lab">forecast skill vs yesterday's sun</div></div></div>""", page=10, note="SIMULATED village on REAL weather · reports/proof.json")

    s(f"""<div class="kick">Fairness and water</div><h2>More tenants served, fairer access, and the groundwater cap held.</h2>
<div class="grid g3"><div><div class="big">{v['tenant_D']}</div><div class="lab">of tenant water need met by solar (baseline {v['tenant_B']})</div></div>
<div><div class="big">{v['gini_D']}</div><div class="lab">Gini of access (baseline {v['gini_B']}; lower is fairer)</div></div>
<div><div class="big">{v['budget_exceed_D']}</div><div class="lab">of runs over the seasonal cap (baseline {v['budget_exceed_B']})</div></div></div>
<p style="margin-top:48px;font-size:26px"><b style="color:var(--sun)">Negative results.</b> Monsoon weeks: planner gain {v['neg_mon']} vs {v['neg_dry']} in the dry season. The cap holds back {v['budget_lost']} m³ of solar water a year, which goes to diesel sellers on the same aquifer unless they share the budget.</p>""", page=11)

    s(f"""<div class="kick">Business model</div><h2>Five payers. The pump earns more, the farmer pays less.</h2>
<table><tr><th>Revenue line</th><th>Payer</th><th>Simulated per pump-year</th></tr>
<tr><td>Water per m³</td><td>Farmer</td><td class="d">{v['rsm3_D']}/m³</td></tr>
<tr><td>Mill, chaff cutter, battery packs</td><td>Mill and battery users</td><td class="d">{v['rev_mill_D']} mill · {v['rev_batt_D']} packs</td></tr>
<tr><td>Platform fee (revenue share)</td><td>Owner / FPO / operator</td><td class="d">{v['platform_D']}</td></tr>
<tr><td>Verification receipts</td><td>CSR, lenders, programmes</td><td class="d">per receipt (to price)</td></tr>
<tr><td>Retrofit kit</td><td>Owner via financing</td><td class="d">vendor quote pending</td></tr></table>
<p style="margin-top:28px;font-size:26px">Total revenue {v['rev_D']} vs {v['rev_B']} baseline · Saur Mitra {v['mitra_D']}/month · payback {v['payback_D']} years on a ₹{C.get('unit_capex_rs'):,} unit.</p>""", page=12, note="ASSUMPTION prices swept in the sensitivity analysis")

    s("""<div class="kick">Rollout</div><h2>Start on pumps that already exist.</h2>
<ol style="margin-top:48px;padding-left:40px"><li>Pilot: retrofit existing shared pumps in Samastipur with drive telemetry and the edge controller.</li>
<li>Operators: offer the platform to per-m³ operators and Schneider's Access to Energy partners.</li>
<li>District and state: propose the Anudan Meter pilot (receipts as diesel-subsidy claims) to the agriculture department.</li>
<li>National: PM-KUSUM pumps via the optional universal controller; farmer IDs.</li></ol>""", page=13)

    s(f"""<div class="kick">Impact at scale (labelled estimates)</div><h2>Per pump-year, from the simulation; multiply only after a pilot confirms it.</h2>
<div class="grid g3"><div><div class="big">{v['solar_m3_D']}</div><div class="lab">m³ of solar water per pump-year</div></div>
<div><div class="big">{v['diesel_D']} L</div><div class="lab">diesel avoided per pump-year</div></div>
<div><div class="big">{C.get('kusum_standalone_pumps'):,}+</div><div class="lab">standalone solar pumps installed under PM-KUSUM <span class="tag">PUBLISHED</span></div></div></div>""", page=14, note="Estimates, not measurements")

    s("""<div class="kick">Team and ask</div><h2>Help us put SinchaiSlot on ten real pumps in Samastipur.</h2>
<p style="margin-top:40px">Ask: Altivar Solar drives for a ten-pump pilot, access to an operator's field data, and a Schneider mentor for the EcoStruxure integration.</p>
<p style="margin-top:40px;color:var(--mist)">[Team names and roles: to be added by the team]</p>""", cls="", page=15)

    html = f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>SinchaiSlot deck</title><style>{CSS}</style></head><body>{''.join(slides)}</body></html>"
    p = out_dir / "deck.html"
    p.write_text(html)
    _ = src
    return p
