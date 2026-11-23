"use client";

import { useMemo, useState } from "react";
import { BandChart, BandLegend } from "@/components/BandChart";
import { Gantt } from "@/components/Gantt";
import { Shell } from "@/components/Shell";
import { Btn, ErrorNote, Panel, SourceTag, Stat } from "@/components/ui";
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

const HOURS = Array.from({ length: 12 }, (_, i) => `${String(6 + i).padStart(2, "0")}:00`);

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

  return (
    <Shell title="Surya Planner">
      <ErrorNote error={error} />
      <div className="grid min-w-0 gap-4">
        <Panel
          title={<span className="flex items-center gap-2">Today&apos;s plan, plan v{snap?.plan_version ?? "–"} <SourceTag kind="model" /></span>}
          right={<span className="text-[11px] text-mist">Two-stage stochastic MILP (HiGHS) over P10 / P50 / P90 sun</span>}
        >
          {snap && <div role="region" className="overflow-x-auto" tabIndex={0} aria-label="Plan timeline, scrolls sideways on small screens"><div className="min-w-[720px]"><Gantt slots={snap.slots} nowIndex={now} highlight={moved} /></div></div>}
          <div className="mt-4">
            {snap && (
              <BandChart
                labels={snap.forecast.labels}
                q10={snap.forecast.q10}
                q50={snap.forecast.q50}
                q90={snap.forecast.q90}
                actual={snap.forecast.actual}
                actualUpTo={now}
                nowIndex={now}
                height={170}
              />
            )}
            <div className="mt-1">
              <BandLegend />
            </div>
          </div>
        </Panel>
        <div className="grid min-w-0 gap-4 lg:grid-cols-2">
          <Panel title="Why the plan changed">
            {!snap?.diffs.length && <p className="text-sm text-mist">No re-plans yet. At 13:40 the nowcast replaces the afternoon forecast with what the sky is doing.</p>}
            <ol className="flex flex-col gap-3">
              {[...(snap?.diffs ?? [])].reverse().map((d) => (
                <li key={d.version} className="rounded-md border border-soil p-3">
                  <div className="flex items-baseline justify-between text-[12px] text-mist">
                    <span className="num">v{d.version} · {d.at}</span>
                    <span>{d.reason}</span>
                  </div>
                  <ul className="mt-2 flex flex-col gap-1.5 break-words text-[13px]">
                    {d.changes.length === 0 && <li className="text-mist">No slot moved.</li>}
                    {d.changes.map((c, i) => (
                      <li key={i}>
                        <div>{c.reason_en}</div>
                        <div className="deva text-[12.5px] text-mist" lang="hi">{c.reason_hi}</div>
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ol>
          </Panel>
          <Panel title="Drag a cloud: what if the sun drops?" right={<span className="text-[11px] text-mist">runs the solver, does not change the plan</span>}>
            <form
              className="grid gap-3 text-[13px] sm:grid-cols-3"
              onSubmit={(e) => {
                e.preventDefault();
                simulate();
              }}
            >
              <label className="flex flex-col gap-1">
                From
                <select value={from} onChange={(e) => setFrom(e.target.value)} className="rounded border border-soil bg-night px-2 py-1.5">
                  {HOURS.map((h) => <option key={h}>{h}</option>)}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                To
                <select value={to} onChange={(e) => setTo(e.target.value)} className="rounded border border-soil bg-night px-2 py-1.5">
                  {HOURS.map((h) => <option key={h}>{h}</option>)}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                Sun lost: <span className="num">{cut}%</span>
                <input type="range" min={10} max={100} step={10} value={cut} onChange={(e) => setCut(Number(e.target.value))} className="accent-[var(--sun)]" />
              </label>
              <div className="sm:col-span-3">
                <Btn type="submit" tone="sun" disabled={busy}>{busy ? "Solving…" : "Simulate this cloud"}</Btn>
              </div>
            </form>
            {whatIf && (
              <div className="mt-4 grid gap-3">
                <div className="grid grid-cols-3 gap-3">
                  <Stat value={`${fmt.n(whatIf.water_m3_p50_before)}→${fmt.n(whatIf.water_m3_p50_after)}`} unit="m³" label="Water (P50)" tone="water" />
                  <Stat value={`${fmt.n(whatIf.mill_kwh_before, 1)}→${fmt.n(whatIf.mill_kwh_after, 1)}`} unit="kWh" label="Mill" tone="sun" />
                  <Stat value={fmt.n(whatIf.battery_kwh_after, 1)} unit="kWh" label="Batteries after" />
                </div>
                <ul className="flex flex-col gap-1 text-[13px]">
                  {whatIf.changes.length === 0 && <li className="text-mist">No slot would move.</li>}
                  {whatIf.changes.map((c, i) => <li key={i}>{c.reason_en}</li>)}
                </ul>
              </div>
            )}
          </Panel>
        </div>
      </div>
    </Shell>
  );
}
