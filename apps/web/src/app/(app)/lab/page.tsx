"use client";

import { scaleLinear } from "d3-scale";
import { line } from "d3-shape";
import { Shell } from "@/components/Shell";
import { ErrorNote, Panel, SourceTag, Stat } from "@/components/ui";
import { fmt, useApi } from "@/lib/api";
import type { Band, Proof } from "@/lib/types";

const NAMES: Record<string, string> = {
  A: "A · Owner-only",
  B: "B · Chakhaji first-come",
  C: "C · Oorja-style",
  "C+loads": "C + same loads, greedy",
  D: "D · SinchaiSlot",
  "D-nobudget": "D without water budget",
  "D-persistence": "D on yesterday's sun",
  "D-oracle": "D with perfect forecast",
  "D-noisy": "D with a degraded forecast",
};
const COLOR: Record<string, string> = { A: "#6b7a72", B: "#C9A86A", C: "#7FA3B8", "C+loads": "#6C8C9E", D: "var(--sun)" };

type Evals = {
  agent?: { cases: number; case_success: number; tool_call_accuracy: number; booking_success: number; wrong_booking_rate: number; reply_language_match: number; latency_ms_p50: number };
  first_heldout_run?: { cases: number; case_success: number; booking_success: number; wrong_booking_rate: number; passes_thresholds: boolean };
  agent_label?: string;
  passes_thresholds?: boolean;
  thresholds?: Record<string, number>;
  asr_robustness?: { label: string; points: { simulated_word_noise: number; wer: number; case_success: number; wrong_booking_rate: number }[] };
  optimiser_benchmark?: { by_size: Record<string, { solve_s_median: number; solve_s_max: number; gap_max: number; binaries_median: number }> };
};

export default function LabPage() {
  const { data: p, error } = useApi<Proof>("/api/proof");
  const { data: ev } = useApi<Evals>("/api/evals");
  const pol = p?.policies;
  const keys = ["A", "B", "C", "C+loads", "D"].filter((k) => pol?.[k]);
  const ablate = ["D", "D-nobudget", "D-persistence", "D-oracle", "D-noisy"].filter((k) => pol?.[k]);
  const g = p?.gains;
  return (
    <Shell title="Prayogshala: the proof">
      <ErrorNote error={error} />
      {p && pol && (
        <div className="grid min-w-0 gap-4">
          <p className="max-w-4xl text-[13px] text-mist">
            Every number on this page is read from <code className="num">reports/proof.json</code>, written by <code className="num">make proof</code>:
            {" "}{p.setup.runs_per_policy} simulated years per policy ({p.setup.seeds} synthetic villages × held-out weather years{" "}
            {p.setup.years.join(", ")}), real NASA POWER sun and real archived forecasts. Bands are P10 to P90 across runs.{" "}
            <SourceTag kind="real" /> weather · <SourceTag kind="simulated" /> village, pump and bookings.
          </p>
          <Panel>
            <div className="grid gap-6 p-1 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:items-end">
              <div>
                <div className="text-[12px] text-mist">Sun put to work by SinchaiSlot, per kWp of panels per year</div>
                <div className="num mt-2 text-6xl leading-none text-sun md:text-8xl">{fmt.n(pol.D.utilisation_kwh_per_kwp.p50)}<span className="ml-2 whitespace-nowrap text-lg text-mist">kWh/kWp·yr</span></div>
                <div className="mt-3 text-[13px] text-fog">
                  vs <span className="num text-white">{fmt.n(pol.B.utilisation_kwh_per_kwp.p50)}</span> for first-come hourly sales (Chakhaji baseline):{" "}
                  <span className="num text-sun">{fmt.signedPct(g?.utilisation_D_vs_B.p50)}</span> <span className="text-mist">({bandTxt(g?.utilisation_D_vs_B, true)})</span>
                </div>
              </div>
              <dl className="grid grid-cols-1 divide-y divide-soil border-y border-soil sm:grid-cols-3 sm:divide-x sm:divide-y-0">
                <div className="px-0 py-3 sm:px-4">
                  <dt className="text-[12px] text-mist">Farmer price, solar water</dt>
                  <dd className="num mt-1 text-3xl text-water">₹{pol.D.farmer_rs_per_m3_solar.p50.toFixed(2)}<span className="ml-1 text-sm text-mist">/m³</span></dd>
                  <dd className="num mt-1 text-[12px] text-mist">B ₹{pol.B.farmer_rs_per_m3_solar.p50.toFixed(2)} · diesel ₹{p.headline.diesel_rs_per_m3.toFixed(2)}</dd>
                </div>
                <div className="px-0 py-3 sm:px-4">
                  <dt className="text-[12px] text-mist">Tenant need met by solar</dt>
                  <dd className="num mt-1 text-3xl text-white">{fmt.pct(pol.D.tenant_share_served_by_solar.p50)}</dd>
                  <dd className="num mt-1 text-[12px] text-mist">B {fmt.pct(pol.B.tenant_share_served_by_solar.p50)}</dd>
                </div>
                <div className="px-0 py-3 sm:px-4">
                  <dt className="text-[12px] text-mist">Fairness (Gini, lower is fairer)</dt>
                  <dd className="num mt-1 text-3xl text-white">{pol.D.gini_solar_share_by_household.p50.toFixed(2)}</dd>
                  <dd className="num mt-1 text-[12px] text-mist">B {pol.B.gini_solar_share_by_household.p50.toFixed(2)}</dd>
                </div>
              </dl>
            </div>
          </Panel>

          <div className="grid min-w-0 gap-4 xl:grid-cols-2">
            <Panel title={<Finding kicker="Solar kWh used per kWp per year">SinchaiSlot puts {fmt.n(pol.D.utilisation_kwh_per_kwp.p50)} to work; first-come hourly sales, {fmt.n(pol.B.utilisation_kwh_per_kwp.p50)}.</Finding>} right={<span className="text-[11px] text-mist">bars P50, whiskers P10-P90</span>}>
              <Bars rows={keys.map((k) => ({ k, b: pol[k].utilisation_kwh_per_kwp }))} digits={0} />
            </Panel>
            <Panel title={<Finding kicker="Share of tenant water need met by solar">Tenants get {fmt.pct(pol.D.tenant_share_served_by_solar.p50)} of their need from the sun, against {fmt.pct(pol.B.tenant_share_served_by_solar.p50)}.</Finding>}>
              <Bars rows={keys.map((k) => ({ k, b: pol[k].tenant_share_served_by_solar }))} pct />
            </Panel>
            <Panel title={<Finding kicker="Diesel avoided per pump-year">{fmt.n(pol.D.diesel_l_avoided.p50)} litres of diesel avoided a year; the groundwater cap holds some water back.</Finding>} right={<SourceTag kind="published" />}>
              <Bars rows={keys.map((k) => ({ k, b: pol[k].diesel_l_avoided }))} digits={0} unit=" L" />
            </Panel>
            <Panel title="Pump owner / FPO income and Saur Mitra income">
              <table className="num w-full text-[13px]">
                <thead className="text-left text-[11px] text-mist">
                  <tr><th className="pb-1 font-normal">Policy</th><th className="pb-1 text-right font-normal">Revenue ₹/yr</th><th className="pb-1 text-right font-normal">Owner/FPO ₹/yr</th><th className="pb-1 text-right font-normal">Saur Mitra ₹/mo</th><th className="pb-1 text-right font-normal">Payback yr</th></tr>
                </thead>
                <tbody>
                  {keys.map((k) => (
                    <tr key={k} className="border-t border-soil">
                      <td className="py-1.5 font-sans">{NAMES[k]}</td>
                      <td className="text-right">{fmt.n(pol[k].revenue_rs.p50)}</td>
                      <td className="text-right">{fmt.n(pol[k].owner_fpo_income_rs.p50)}</td>
                      <td className="text-right">{fmt.n(pol[k].saur_mitra_rs_per_month?.p50)}</td>
                      <td className="text-right">{pol[k].payback_years ? pol[k].payback_years.p50.toFixed(1) : "–"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-2 text-[12px] text-mist">Owner income in A and B counts the owner&apos;s own water at the diesel price. D splits revenue with the Saur Mitra (25%) and the platform (10%) <SourceTag kind="assumption" />.</p>
            </Panel>
          </div>

          <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
            <Panel title="Weekly solar used, one village, first held-out year">
              {p.weekly_example?.D && <Weekly p={p} />}
            </Panel>
            <Panel title="Where the gain comes from (ablations)">
              <Bars rows={ablate.map((k) => ({ k, b: pol[k].utilisation_kwh_per_kwp }))} digits={0} />
              <ul className="mt-3 flex flex-col gap-1 text-[13px]">
                {g?.utilisation_D_vs_Cloads && <li>Planner vs the same loads run greedily: <b className="num">{fmt.signedPct(g.utilisation_D_vs_Cloads.p50, 1)}</b> <span className="text-mist">{bandTxt(g.utilisation_D_vs_Cloads, true)}</span></li>}
                {g?.utilisation_D_vs_Dpersistence && <li>Forecast vs yesterday&apos;s sun: <b className="num">{fmt.signedPct(g.utilisation_D_vs_Dpersistence.p50, 1)}</b></li>}
                {g?.utilisation_Doracle_vs_D && <li>Headroom left to a perfect forecast: <b className="num">{fmt.signedPct(g.utilisation_Doracle_vs_D.p50, 1)}</b></li>}
              </ul>
            </Panel>
          </div>

          <div className="grid min-w-0 gap-4 xl:grid-cols-2">
            <Panel title={<Finding kicker="Honest results: what the planner does and does not add">Not everything wins, and the report says where.</Finding>} right={<span className="rounded bg-sun/10 px-2 py-0.5 text-[11px] text-sun">negative result</span>}>
              <div className="grid grid-cols-2 gap-4">
                <Stat value={fmt.signedPct(p.negative_results.gain_vs_Cloads_monsoon, 1)} label="Gain vs greedy loads, monsoon weeks" />
                <Stat value={fmt.signedPct(p.negative_results.gain_vs_Cloads_dry, 1)} label="Gain vs greedy loads, dry season" />
              </div>
              <ul className="mt-3 flex list-disc flex-col gap-2 pl-5 text-[13px] text-fog">
                {((p.negative_results.statements as string[] | undefined) ?? [p.negative_results.explanation ?? ""]).map((t, i) => <li key={i}>{t}</li>)}
              </ul>
            </Panel>
            <Panel title="Sensitivity of the headline to assumptions" right={<SourceTag kind="assumption" />}>
              <table className="num w-full text-[12.5px]">
                <tbody>
                  {Object.entries(p.sensitivity).map(([name, pts]) => (
                    <tr key={name} className="border-t border-soil">
                      <td className="py-1.5 font-sans text-fog">{name.replaceAll("_", " ")}</td>
                      {pts.map((pt, i) => (
                        <td key={i} className="py-1.5 text-right">
                          <span className="text-mist">{Object.values(pt.setting)[0]}</span> → {fmt.n(pt.utilisation_kwh_per_kwp)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-2 text-[12px] text-mist">Values: setting → SinchaiSlot kWh/kWp/yr (median of runs).</p>
            </Panel>
          </div>

          <div className="grid min-w-0 gap-4 xl:grid-cols-3">
            <Panel title="Solar forecast, held-out years" right={<SourceTag kind="real" />}>
              <div className="grid grid-cols-2 gap-3">
                <Stat value={fmt.pct(p.forecast.skill_vs_persistence)} label="Better than yesterday's sun" tone="sun" />
                <Stat value={fmt.pct(p.forecast.skill_vs_climatology)} label="Better than climatology" tone="sun" />
              </div>
              <p className="num mt-3 text-[12px] text-mist">
                Pinball loss {p.forecast.sinchaislot_meta.pinball_w_m2} W/m² vs {p.forecast.persistence.pinball_w_m2} (persistence) and{" "}
                {p.forecast.climatology.pinball_w_m2} (climatology); P10-P90 coverage {fmt.pct(p.forecast.sinchaislot_meta.p10_p90_coverage)} (target 80%);
                trained {p.forecast.train_years.join("-")}, tested {p.forecast.test_years.join("-")}, {fmt.n(p.forecast.n_test_hours)} daylight hours.
              </p>
            </Panel>
            <Panel title="Saathi agent, held-out test set">
              {ev?.first_heldout_run ? (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    <Stat value={fmt.pct(ev.first_heldout_run.case_success)} label={`Conversations right (${ev.first_heldout_run.cases})`} />
                    <Stat value={fmt.pct(ev.first_heldout_run.wrong_booking_rate, 1)} label="Wrong bookings" tone="leaf" />
                    <Stat value={fmt.pct(ev.first_heldout_run.booking_success)} label="Bookings completed" />
                    <Stat value={ev.first_heldout_run.passes_thresholds ? "yes" : "no"} label="Met pre-set thresholds" tone={ev.first_heldout_run.passes_thresholds ? "default" : "sun"} />
                  </div>
                  {ev.agent && (
                    <p className="mt-3 text-[12px] text-mist">
                      After two fixes: {fmt.pct(ev.agent.case_success)} right, {fmt.pct(ev.agent.booking_success)} bookings completed, wrong bookings {fmt.pct(ev.agent.wrong_booking_rate)}. {ev.agent_label}
                    </p>
                  )}
                </>
              ) : (
                <p className="text-sm text-mist">Run <code>make evals</code>.</p>
              )}
            </Panel>
            <Panel title="Optimiser benchmark">
              {ev?.optimiser_benchmark && (
                <table className="num w-full text-[12.5px]">
                  <thead className="text-left text-[11px] text-mist"><tr><th className="font-normal">Bookings</th><th className="text-right font-normal">Binaries</th><th className="text-right font-normal">Median s</th><th className="text-right font-normal">Gap max</th></tr></thead>
                  <tbody>
                    {Object.entries(ev.optimiser_benchmark.by_size).map(([n, r]) => (
                      <tr key={n} className="border-t border-soil"><td className="py-1">{n}</td><td className="text-right">{r.binaries_median}</td><td className="text-right">{r.solve_s_median}</td><td className="text-right">{(r.gap_max * 100).toFixed(2)}%</td></tr>
                    ))}
                  </tbody>
                </table>
              )}
              <p className="mt-2 text-[12px] text-mist">Gap is against the same model solved to proven optimality (120 s limit).</p>
            </Panel>
          </div>
        </div>
      )}
    </Shell>
  );
}

function bandTxt(b?: Band, pct = false) {
  if (!b) return "";
  const f = (x: number) => (pct ? fmt.signedPct(x) : fmt.n(x));
  return `P10 ${f(b.p10)} to P90 ${f(b.p90)}, n=${b.n}`;
}

function Bars({ rows, digits = 1, pct = false, unit = "" }: { rows: { k: string; b: Band }[]; digits?: number; pct?: boolean; unit?: string }) {
  const max = Math.max(...rows.map((r) => r.b.p90), 1e-9) * 1.05;
  const f = (x: number) => (pct ? fmt.pct(x) : fmt.n(x, digits) + unit);
  return (
    <ul className="flex flex-col gap-2.5" role="list">
      {rows.map(({ k, b }) => (
        <li key={k} className="grid grid-cols-[150px_minmax(0,1fr)_72px] items-center gap-3 text-[12.5px]">
          <span className={k === "D" ? "font-medium text-sun" : "text-fog"}>{NAMES[k] ?? k}</span>
          <span className="relative h-5 rounded-sm bg-night-3/60" aria-hidden>
            <span className="absolute inset-y-0 left-0 rounded-sm" style={{ width: `${(b.p50 / max) * 100}%`, background: COLOR[k] ?? "var(--sun-deep)", opacity: k === "D" ? 1 : 0.8 }} />
            <span className="absolute top-1/2 h-px -translate-y-1/2 bg-white/80" style={{ left: `${(b.p10 / max) * 100}%`, width: `${Math.max(((b.p90 - b.p10) / max) * 100, 0.4)}%` }} />
          </span>
          <span className="num text-right">{f(b.p50)}</span>
        </li>
      ))}
    </ul>
  );
}

function Weekly({ p }: { p: Proof }) {
  const w = p.weekly_example;
  const W = 800, H = 240, pad = { l: 40, r: 10, t: 10, b: 26 };
  const n = w.D.week.length;
  const max = Math.max(...w.D.pv_kwh) * 1.05;
  const x = scaleLinear().domain([0, n - 1]).range([pad.l, W - pad.r]);
  const y = scaleLinear().domain([0, max]).range([H - pad.b, pad.t]);
  const mk = (a: number[]) => line<number>().x((_, i) => x(i)).y((v) => y(v))(a) ?? "";
  const mon = w.D.week.map((d) => [7, 8, 9].includes(Number(d.slice(5, 7))));
  const m0 = mon.indexOf(true), m1 = mon.lastIndexOf(true);
  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Weekly solar energy used by policy">
        {m0 >= 0 && <rect x={x(m0)} y={pad.t} width={x(m1) - x(m0)} height={H - pad.b - pad.t} fill="var(--water)" opacity="0.08" />}
        <path d={`${mk(w.D.pv_kwh)} L ${x(n - 1)} ${y(0)} L ${x(0)} ${y(0)} Z`} fill="var(--sun)" opacity="0.12" />
        {["B", "C+loads", "D"].filter((k) => w[k]).map((k) => (
          <path key={k} d={mk(w[k].useful_kwh)} fill="none" stroke={k === "D" ? "var(--sun)" : k === "B" ? "#C9A86A" : "#6C8C9E"} strokeWidth={k === "D" ? 2.4 : 1.6} strokeDasharray={k === "B" ? "5 4" : undefined} />
        ))}
        {y.ticks(4).map((t) => <text key={t} x={pad.l - 6} y={y(t) + 4} textAnchor="end" fontSize="11" fill="var(--mist)" className="num">{t}</text>)}
        {w.D.week.map((d, i) => (i % 8 === 0 ? <text key={d} x={x(i)} y={H - 6} fontSize="11" fill="var(--mist)" textAnchor="middle" className="num">{d.slice(5)}</text> : null))}
      </svg>
      <figcaption className="mt-1 flex flex-wrap gap-4 text-[12px] text-mist">
        <span><span className="mr-1 inline-block h-2 w-4 bg-sun/30" />solar available</span>
        <span><span className="mr-1 inline-block h-0.5 w-4 bg-sun align-middle" />D SinchaiSlot</span>
        <span><span className="mr-1 inline-block h-0.5 w-4 bg-[#6C8C9E] align-middle" />C + loads</span>
        <span><span className="mr-1 inline-block w-4 border-t border-dashed border-[#C9A86A] align-middle" />B Chakhaji</span>
        <span><span className="mr-1 inline-block h-2 w-4 bg-water/20" />monsoon</span>
        <span>kWh per week</span>
      </figcaption>
    </figure>
  );
}

function Finding({ kicker, children }: { kicker: string; children: React.ReactNode }) {
  return (
    <span className="block py-1">
      <span className="block text-[11.5px] font-normal text-mist">{kicker}</span>
      <span className="mt-1 block font-serif text-[19px] font-normal leading-snug text-white">{children}</span>
    </span>
  );
}
