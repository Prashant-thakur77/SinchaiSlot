"use client";

import { useMemo, useRef, useState } from "react";
import { BandChart, BandLegend } from "@/components/BandChart";
import { Gantt } from "@/components/Gantt";
import { Shell } from "@/components/Shell";
import { Btn, ErrorNote, Roll, SourceTag } from "@/components/ui";
import { fmt, postJSON, useApi } from "@/lib/api";
import type { Change, Snapshot } from "@/lib/types";

type WhatIf = {
  water_m3_p50_before: number;
  water_m3_p50_after: number;
  mill_kwh_before: number;
  mill_kwh_after: number;
  battery_kwh_after: number;
  changes: Change[];
};

const HOURS_ALL = Array.from({ length: 25 }, (_, i) => `${String(6 + Math.floor(i / 2)).padStart(2, "0")}:${i % 2 ? "30" : "00"}`);

export default function PlannerPage() {
  const { data: snap, error } = useApi<Snapshot>("/api/state", 1500);
  const [from, setFrom] = useState("13:00");
  const [to, setTo] = useState("15:00");
  const [cut, setCut] = useState(50);
  const [whatIf, setWhatIf] = useState<WhatIf | null>(null);
  const [busy, setBusy] = useState(false);
  const now = useMemo(() => {
    if (!snap) return -1;
    const [h, m] = snap.clock.split(":").map(Number);
    return Math.floor(((h - 6) * 60 + m) / 30);
  }, [snap]);
  const lastDiff = snap?.diffs[snap.diffs.length - 1];
  const moved = new Set((lastDiff?.changes ?? []).map((c) => c.subject));

  const simulate = async () => {
    setBusy(true);
    try {
      setWhatIf(
        await postJSON<WhatIf>("/api/tools/what_if", { args: { cloud_factor: 1 - cut / 100, from_hhmm: from, to_hhmm: to } }, "dev-operator-token"),
      );
    } finally {
      setBusy(false);
    }
  };

  // Drag across the forecast to place a cloud: x maps to the chart's slot axis (BandChart: pad.l 38, pad.r 8 of 1000).
  const chartRef = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<number | null>(null);
  const idxAt = (clientX: number) => {
    const r = chartRef.current?.getBoundingClientRect();
    if (!r) return 0;
    const vx = ((clientX - r.left) / r.width) * 1000;
    return Math.max(0, Math.min(24, Math.round(((vx - 38) / 954) * 23)));
  };
  const lab = (i: number) => `${String(6 + Math.floor(i / 2)).padStart(2, "0")}:${i % 2 ? "30" : "00"}`;
  const fromI = HOURS_ALL.indexOf(from);
  const toI = HOURS_ALL.indexOf(to);
  const leftPct = ((38 + (Math.max(0, fromI) / 23) * 954) / 1000) * 100;
  const rightPct = ((38 + (Math.max(0, Math.min(23, toI)) / 23) * 954) / 1000) * 100;

  return (
    <Shell title="Surya Planner">
      <ErrorNote error={error} />
      <div className="grid min-w-0 gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <section aria-label="Today's plan" className="min-w-0">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 text-[12px] text-mist">Plan v{snap?.plan_version ?? "–"} · two-stage stochastic MILP over P10 / P50 / P90 sun <SourceTag kind="model" /></div>
              <h2 className="mt-1 font-display text-[clamp(1.6rem,2.6vw,2.3rem)] font-semibold leading-tight tracking-tight">
                Water first: <span className="text-water"><Roll value={fmt.n(snap?.summary.water_m3_p50, 0)} /> m³</span> planned, then <span className="text-sun"><Roll value={fmt.n((snap?.summary.mill_kwh_p50 ?? 0) + (snap?.summary.chaff_kwh_p50 ?? 0) + (snap?.summary.battery_kwh_p50 ?? 0), 1)} /> kWh</span> for the mill and batteries.
              </h2>
            </div>
            <span className="num text-[12px] text-mist">P10 keeps {fmt.n(snap?.summary.water_m3_p10, 0)} m³ even on a dim day</span>
          </div>

          {/* The sky over the plan: drag to place a cloud */}
          <div className="mt-5 rounded-[14px] border border-soil bg-night-2 p-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="text-[13px] font-medium text-fog">Sun the plan is built on</h3>
              <span className="text-[11.5px] text-mist">Drag across the sky to place a cloud</span>
            </div>
            <div
              ref={chartRef}
              className="relative mt-2 cursor-crosshair touch-none select-none"
              onPointerDown={(e) => { (e.target as HTMLElement).setPointerCapture?.(e.pointerId); const i = idxAt(e.clientX); setDrag(i); setFrom(lab(i)); setTo(lab(Math.min(24, i + 1))); setWhatIf(null); }}
              onPointerMove={(e) => { if (drag === null) return; const i = idxAt(e.clientX); setFrom(lab(Math.min(drag, i))); setTo(lab(Math.max(drag, i) + (i === drag ? 1 : 0))); }}
              onPointerUp={() => setDrag(null)}
            >
              {snap && <BandChart labels={snap.forecast.labels} q10={snap.forecast.q10} q50={snap.forecast.q50} q90={snap.forecast.q90} actual={snap.forecast.actual} actualUpTo={now} nowIndex={now} height={190} />}
              {fromI >= 0 && toI > fromI && (
                <div className="pointer-events-none absolute top-[4%] h-[78%] transition-[left,width] duration-150" style={{ left: `${leftPct}%`, width: `${Math.max(1, rightPct - leftPct)}%` }} aria-hidden>
                  <div className="h-full w-full rounded-[40%] bg-[radial-gradient(closest-side,rgba(70,88,96,.78),rgba(70,88,96,0))]" style={{ opacity: 0.35 + cut / 140 }} />
                  <span className="num absolute -top-1 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-night/85 px-1.5 text-[11px] text-fog">{from}–{to} · −{cut}% sun</span>
                </div>
              )}
            </div>
            <div className="mt-1"><BandLegend /></div>
            <form className="mt-3 flex flex-wrap items-end gap-3 text-[12.5px]" onSubmit={(e) => { e.preventDefault(); simulate(); }}>
              <label className="flex flex-col gap-1 text-mist">From
                <select value={from} onChange={(e) => setFrom(e.target.value)} className="num rounded border border-soil bg-night px-2 py-1.5 text-fog">{HOURS_ALL.map((h) => <option key={h}>{h}</option>)}</select>
              </label>
              <label className="flex flex-col gap-1 text-mist">To
                <select value={to} onChange={(e) => setTo(e.target.value)} className="num rounded border border-soil bg-night px-2 py-1.5 text-fog">{HOURS_ALL.map((h) => <option key={h}>{h}</option>)}</select>
              </label>
              <label className="flex min-w-[160px] flex-1 flex-col gap-1 text-mist">Sun lost under the cloud: <span className="num text-fog">{cut}%</span>
                <input type="range" min={10} max={100} step={10} value={cut} onChange={(e) => setCut(Number(e.target.value))} className="accent-[var(--sun)]" />
              </label>
              <Btn type="submit" tone="sun" disabled={busy}>{busy ? "Solving…" : "What would move?"}</Btn>
            </form>
            {whatIf && (
              <div className="mt-4 border-t border-soil pt-3" role="status">
                <p className="text-[14px] text-fog">
                  Water <span className="num text-water">{fmt.n(whatIf.water_m3_p50_before)} → {fmt.n(whatIf.water_m3_p50_after)} m³</span>, mill <span className="num text-sun">{fmt.n(whatIf.mill_kwh_before, 1)} → {fmt.n(whatIf.mill_kwh_after, 1)} kWh</span>, batteries end at <span className="num">{fmt.n(whatIf.battery_kwh_after, 1)} kWh</span>. Nothing is changed until the real sky does this.
                </p>
                <ul className="mt-2 flex flex-col gap-1 text-[13px] text-mist">
                  {whatIf.changes.length === 0 && <li>No slot would move.</li>}
                  {whatIf.changes.map((c, i) => <li key={i}>{c.reason_en}</li>)}
                </ul>
              </div>
            )}
          </div>

          {/* The plan itself, slot by slot, on the same time axis */}
          <div className="mt-5">
            <h3 className="mb-2 text-[13px] font-medium text-fog">Who gets the sun, slot by slot</h3>
            {snap && <div role="region" className="overflow-x-auto" tabIndex={0} aria-label="Plan timeline, scrolls sideways on small screens"><div className="min-w-[720px]"><Gantt slots={snap.slots} nowIndex={now} highlight={moved} /></div></div>}
          </div>
        </section>

        {/* Plan changes as a dated log */}
        <aside aria-label="Why the plan changed" className="min-w-0">
          <h2 className="text-[13px] font-medium text-fog">Why the plan changed</h2>
          {!snap?.diffs.length && <p className="mt-2 text-sm text-mist">No re-plans yet. At 13:40 the nowcast replaces the afternoon forecast with what the sky is actually doing; click 13:45 on the day bar.</p>}
          <ol className="mt-3 flex flex-col border-l border-soil">
            {[...(snap?.diffs ?? [])].reverse().map((d) => (
              <li key={d.version} className="relative pb-5 pl-5">
                <span className="absolute -left-[5px] top-1 h-[9px] w-[9px] rounded-full bg-water" aria-hidden />
                <div className="num text-[12px] text-water">{d.at} · plan v{d.version}</div>
                <div className="text-[12px] text-mist">{d.reason}</div>
                <ul className="mt-2 flex flex-col gap-2 break-words text-[13px]">
                  {d.changes.length === 0 && <li className="text-mist">No slot moved.</li>}
                  {d.changes.map((c, i) => (
                    <li key={i} className="rounded-md bg-night-2 px-3 py-2">
                      <div>{c.reason_en}</div>
                      <div className="deva mt-0.5 text-[12.5px] text-mist" lang="hi">{c.reason_hi}</div>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>
        </aside>
      </div>
    </Shell>
  );
}
