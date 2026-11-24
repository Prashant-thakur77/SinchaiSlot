"use client";

import { scaleLinear } from "d3-scale";
import { line } from "d3-shape";
import { useEffect, useState } from "react";
import { Panel, SourceTag } from "@/components/ui";
import { fmt, useApi } from "@/lib/api";

type Cause = "panels" | "friction" | "water";
type Ex = { onset: string | null; alert: { day: string; cause: Cause } | null; days: string[] } & Record<Cause, (number | null)[]>;
type Doctor = {
  thresholds: Record<Cause, number>; trials: number; found: number; right_cause: number; portal_found: number;
  false_alarms_per_pump_year_at_least: number; portal_false_alarms_per_pump_year_at_least: number;
  by_kind: Record<string, { found_in_60_days: number; median_days: number; trials: number; already_alerting: number }>;
  half_size_faults: { found: number }; example: Record<string, Ex>; advice: Record<string, { en: string; hi: string }>; not_seen: string;
};
const KINDS: [string, string][] = [["healthy", "Nothing wrong"], ["panels_dust", "Dust builds up"], ["panels_shade", "Module fails"], ["friction", "Bearing wears"], ["water", "Water drops"]];
const SIGN: Record<Cause, { name: string; col: string }> = {
  panels: { name: "Sun lost", col: "var(--sun-deep)" }, friction: { name: "Working harder", col: "var(--fault)" }, water: { name: "Lifting higher", col: "var(--water-deep)" },
};

export function PumpDoctor() {
  const { data: r } = useApi<Doctor>("/api/doctor");
  const [kind, setKind] = useState("panels_dust");
  // The panel arrives after the page, so a #doctor link has to scroll once it exists.
  useEffect(() => {
    if (r && location.hash === "#doctor") document.getElementById("doctor")?.scrollIntoView();
  }, [r]);
  if (!r) return null;
  const ex = r.example[kind];
  const cause = ex.alert?.cause ?? "ok";
  return (
    <Panel title="Pump Doctor" right={<SourceTag kind="simulated" />} className="mt-4" id="doctor">
      <div className="grid min-w-0 gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <div className="min-w-0">
          <p className="max-w-[62ch] text-[15px] text-fog">A pump rarely stops on one bad day; it fades. The drive&apos;s own readings, compared with the neighbouring pumps and with last month, show why. Choose what goes wrong on 17 October:</p>
          <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="What goes wrong">
            {KINDS.map(([k, label]) => <button key={k} type="button" aria-pressed={kind === k} onClick={() => setKind(k)} className={`min-h-10 rounded-full border px-4 text-[14px] ${kind === k ? "border-ink bg-ink text-paper" : "border-soil text-fog hover:bg-night-3"}`}>{label}</button>)}
          </div>
          <Chart ex={ex} th={r.thresholds} />
          <ul className="flex flex-wrap gap-x-5 gap-y-1 text-[13px]">
            {(Object.keys(SIGN) as Cause[]).map((c) => <li key={c} className="flex items-center gap-2"><span className="h-[3px] w-5 rounded" style={{ background: SIGN[c].col }} aria-hidden />{SIGN[c].name}</li>)}
            <li className="text-mist">Alert when a line reaches 1</li>
          </ul>
          <div role="status" className={`mt-4 rounded-2xl px-4 py-3 ${ex.alert ? "bg-sun/20" : "bg-leaf/15"}`}>
            <p className="text-[16px] font-medium">{r.advice[cause].en}</p>
            <p className="deva mt-0.5 text-[15px] text-fog" lang="hi">{r.advice[cause].hi}</p>
            {ex.alert && <p className="num mt-1 text-[13px] text-mist">Alert on {day(ex.alert.day)}, {Math.round((+new Date(ex.alert.day) - +new Date(ex.onset!)) / 864e5)} days after it began</p>}
          </div>
        </div>
        <div className="min-w-0 text-[14px]">
          <p className="num text-[40px] font-medium leading-none text-leaf-ink">{fmt.pct(r.found)}</p>
          <p className="mt-1 text-fog">of {r.trials} slow faults found within 60 days, {fmt.pct(r.right_cause)} with the right cause. A portal that watches daily energy found {fmt.pct(r.portal_found)}.</p>
          <table className="num mt-4 w-full text-[13px]">
            <thead className="text-left text-mist"><tr><th className="pb-1 font-normal">Fault</th><th className="pb-1 text-right font-normal">Found</th><th className="pb-1 text-right font-normal">Typical wait</th></tr></thead>
            <tbody>{KINDS.slice(1).map(([k, label]) => <tr key={k} className="border-t border-soil"><td className="py-1.5 font-sans">{label}</td><td className="text-right">{fmt.pct(r.by_kind[k].found_in_60_days)}</td><td className="text-right">{Math.round(r.by_kind[k].median_days)} days</td></tr>)}</tbody>
          </table>
          <p className="mt-3 text-[13px] text-mist">False alarms: {r.false_alarms_per_pump_year_at_least.toFixed(1)} a year per pump (portal {r.portal_false_alarms_per_pump_year_at_least.toFixed(1)}). Faults half this size: {fmt.pct(r.half_size_faults.found)} found. {Object.values(r.by_kind).reduce((a, b) => a + b.already_alerting, 0)} further trials already had an earlier alert and are left out. Cannot see: {r.not_seen.charAt(0).toLowerCase() + r.not_seen.slice(1)} Real weather, injected faults; alert levels set on 2022-23, scored on 2024-25.</p>
        </div>
      </div>
    </Panel>
  );
}

const day = (s: string) => new Date(s).toLocaleDateString("en-IN", { day: "numeric", month: "short" });

function Chart({ ex, th }: { ex: Ex; th: Record<Cause, number> }) {
  const W = 720, H = 230, p = { l: 36, r: 10, t: 14, b: 32 };
  const n = ex.days.length;
  const x = scaleLinear().domain([0, n - 1]).range([p.l, W - p.r]);
  const y = scaleLinear().domain([0, 3]).range([H - p.b, p.t]).clamp(true);
  const at = (d: string) => x(ex.days.indexOf(d));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="mt-3 h-auto w-full" role="img" aria-label={ex.alert ? `Alert for ${ex.alert.cause} on ${day(ex.alert.day)}` : "All three signs stay below the alert level"}>
      {[0, 1, 2, 3].map((t) => <g key={t}><line x1={p.l} x2={W - p.r} y1={y(t)} y2={y(t)} stroke={t === 1 ? "var(--ink)" : "var(--soil)"} strokeDasharray={t === 1 ? "5 5" : undefined} /><text x={p.l - 8} y={y(t) + 4} textAnchor="end" className="text-[13px] max-md:text-[26px]" fill="var(--mist)">{t}</text></g>)}
      {ex.days.map((d, i) => d.endsWith("-01") && <text key={d} x={Math.max(x(i), p.l + 12)} y={H - 5} textAnchor="middle" className="text-[13px] max-md:text-[26px]" fill="var(--mist)">{new Date(d).toLocaleDateString("en-IN", { month: "short" })}</text>)}
      {ex.onset && <line x1={at(ex.onset)} x2={at(ex.onset)} y1={p.t} y2={H - p.b} stroke="var(--mist)" strokeDasharray="2 4" />}
      {(Object.keys(SIGN) as Cause[]).map((c) => <path key={c} d={line<number | null>().defined((v) => v !== null).x((_, i) => x(i)).y((v) => y(Math.max(0, v ?? 0) / th[c]))(ex[c]) ?? ""} fill="none" stroke={SIGN[c].col} strokeWidth="2.5" strokeLinejoin="round" />)}
      {ex.alert && <circle cx={at(ex.alert.day)} cy={y(1)} r="6" fill="var(--paper)" stroke="var(--ink)" strokeWidth="2.5" />}
    </svg>
  );
}
