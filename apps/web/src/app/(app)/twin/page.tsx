"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { skyAt } from "@/components/DayBar";
import { EnergyFlow } from "@/components/EnergyFlow";
import { CropLegend, type PlotFeature, PlotMosaic } from "@/components/PlotMosaic";
import { Shell } from "@/components/Shell";
import { ErrorNote, Readout, Roll, SourceTag } from "@/components/ui";
import { fmt, getJSON, type ServerEvent, useApi, useEvents } from "@/lib/api";
import type { Snapshot, Telemetry } from "@/lib/types";

type Village = {
  plots: { type: "FeatureCollection"; features: PlotFeature[] };
  pumps: { id: string; lon: number; lat: number }[];
  sellers: { id: string; lon: number; lat: number; kind: string; name: string }[];
};

type Feed = { ts: string; kind: string; text: string };

export default function TwinPage() {
  const { data: snap, error } = useApi<Snapshot>("/api/state", 1500);
  const { data: village } = useApi<Village>("/api/village", 5000);
  const [telLive, setTel] = useState<Telemetry | null>(null);
  const { data: drive } = useApi<Telemetry & { pv_kw_available: number; extras: { flow_m3h_true: number } }>("/api/drive", 3000);
  const { data: ledger } = useApi<{ rows: { start: string; m3: number; diesel_l_avoided: number; kind: string }[] }>("/api/ledger?limit=200&kind=water", 4000);
  const tel: Telemetry | null = useMemo(
    () =>
      telLive && (!drive || telLive.ts >= drive.ts)
        ? telLive
        : drive
          ? { ...drive, pv_kw: drive.pv_kw_available, flow_m3h_true: drive.extras?.flow_m3h_true }
          : null,
    [telLive, drive],
  );
  const [feed, setFeed] = useState<Feed[]>([]);
  const [selected, setSelected] = useState<PlotFeature | null>(null);


  const onEvent = useCallback((e: ServerEvent) => {
    if (e.kind === "telemetry") setTel(e as unknown as Telemetry);
    const push = (text: string) =>
      setFeed((f) => {
        const ts = String(e.ts).slice(11, 16);
        if (f.some((x) => x.ts === ts && x.text === text)) return f; // history replay and live stream overlap
        return [{ ts, kind: e.kind, text }, ...f].slice(0, 30);
      });
    if (e.kind === "receipt") {
      const r = e as unknown as { m3: number; diesel_l_avoided: number; co2_kg_avoided: number; receipt_id: string; farmer_ref: string };
      push(`Receipt ${r.receipt_id}: ${r.m3.toFixed(1)} m³ to ${r.farmer_ref}, ${r.diesel_l_avoided.toFixed(2)} L diesel avoided`);
    }
    if (e.kind === "plan") {
      const p = e as unknown as { version: number; reason: string; changes: { reason_en: string }[] };
      if (p.version > 1) push(`Plan v${p.version} (${p.reason}): ${p.changes.length} changes`);
    }
    if (e.kind === "nowcast") push(String((e as unknown as { message: string }).message));
    if (e.kind === "callback") {
      const c = e as unknown as { name: string; language: string };
      push(`Saathi calls ${c.name} (${c.language}) with the new time`);
    }
    if (e.kind === "edge") {
      const ev = e as unknown as { type: string; booking_id?: string; fault?: string };
      if (ev.type === "slot_started") push(`Pump started for booking ${ev.booking_id}`);
      if (ev.type === "drive_fault") push(`Drive fault ${ev.fault}`);
    }
  }, []);
  useEvents(onEvent, ["telemetry", "receipt", "plan", "nowcast", "callback", "edge"]);
  useEffect(() => {
    // Replay what already happened today so the feed is not empty when the page opens mid-day.
    getJSON<ServerEvent[]>("/api/events/recent?limit=400")
      .then((evs) => evs.filter((e) => e.kind !== "telemetry").forEach((e) => onEvent(e)))
      .catch(() => {});
  }, [onEvent]);

  const now = useMemo(() => {
    if (!snap) return -1;
    const [h, m] = snap.clock.split(":").map(Number);
    return Math.floor(((h - 6) * 60 + m) / 30);
  }, [snap]);
  const cur = snap?.slots[now];
  const activeFarmerId = useMemo(() => {
    if (!village || !tel?.active_booking || !cur?.farmer) return null;
    return village.plots.features.find((f) => f.properties.farmer === cur.farmer)?.properties.farmer_id ?? null;
  }, [village, tel, cur]);

  const pv = tel?.pv_kw ?? 0;
  const todays = (ledger?.rows ?? []).filter((r) => snap && r.start.startsWith(snap.day));
  const today = {
    m3: todays.reduce((a, r) => a + r.m3, 0),
    diesel: todays.reduce((a, r) => a + r.diesel_l_avoided, 0),
    n: todays.length,
  };
  const loadKw = cur ? (cur.action === "mill" ? cur.mill_kwh * 2 : cur.action === "chaff" ? cur.chaff_kwh * 2 : 0) : 0;
  const batKw = cur ? Math.min(cur.battery_kwh * 2, Math.max(pv - (tel?.power_kw ?? 0) - loadKw, 0)) : 0;
  const zaidUsed = snap?.budget.used_m3?.zaid ?? 0;
  const zaidCap = snap ? snap.budget.annual_m3 * 0.4 : 1;

  const nowMin = snap ? Number(snap.clock.slice(0, 2)) * 60 + Number(snap.clock.slice(3, 5)) : 360;
  const running = !!tel?.active_booking;

  return (
    <Shell title="Village Twin">
      <ErrorNote error={error} />
      <div className="grid min-w-0 gap-x-6 gap-y-5 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        {/* Stage: the command area itself, lit by the hour */}
        <section aria-label="Command area of pump P1" className="relative min-w-0 overflow-hidden rounded-[20px] border border-soil bg-night-2">
          <div className="pointer-events-none absolute inset-0 transition-[background] duration-1000"
            style={{ background: `radial-gradient(70% 60% at ${15 + ((nowMin - 360) / 720) * 70}% 0%, ${skyAt(nowMin, snap?.cloud_applied)}, transparent 70%)` }} aria-hidden />
          <div className="relative flex flex-wrap items-start justify-between gap-3 px-5 pt-4">
            <div>
              <div className="flex items-center gap-2 text-[12px] text-mist">Command area · pump P1 <SourceTag kind="simulated" /></div>
              <div className="mt-1 h-lead">
                {running && cur?.farmer ? <>Water is going to <span className="text-water-ink">{cur.farmer}</span></> : cur?.action === "mill" ? <>The sun is turning the <span className="text-sun-ink">flour mill</span></> : cur?.action === "battery" ? <>Leftover sun is <span className="text-sun-ink">charging battery packs</span></> : <>{village ? village.plots.features.length : "–"} plots, one pump</>}
              </div>
            </div>
            <CropLegend />
          </div>
          <div className="relative grid min-w-0 gap-2 px-3 pb-4 md:grid-cols-[minmax(0,1fr)_230px] md:px-5">
            <div className="relative mx-auto w-full max-w-[640px]">
              {village ? (
                <PlotMosaic features={village.plots.features} pump={village.pumps[0]} sellers={village.sellers} activeFarmer={activeFarmerId}
                  selected={selected?.properties.plot_id} onSelect={setSelected} cloud={!!snap?.cloud_applied && now >= 15 && now <= 20} />
              ) : (
                <div className="aspect-square animate-pulse rounded bg-night-3" />
              )}
            </div>
            <div className="self-end text-[13px]" aria-live="polite">
              {selected ? (
                <div className="rounded-lg border border-ink/10 bg-paper p-3 text-ink shadow-[0_10px_30px_rgba(110,80,30,.22)]">
                  <div className="deva text-[16px] font-semibold">{selected.properties.farmer}</div>
                  <div className="text-[12px] text-ink/70">{selected.properties.tenant ? "Tenant" : selected.properties.owner ? "Pump owner" : "Landholder"} · {selected.properties.language}</div>
                  <dl className="num mt-2 grid grid-cols-2 gap-y-1 border-t border-ink/10 pt-2 text-[12px]">
                    <dt className="text-ink/60">Crop</dt><dd>{selected.properties.crop} ({selected.properties.stage})</dd>
                    <dt className="text-ink/60">Area</dt><dd>{selected.properties.area_ha.toFixed(2)} ha</dd>
                    <dt className="text-ink/60">FAO-56 need</dt><dd>{selected.properties.need_m3.toFixed(0)} m³</dd>
                    <dt className="text-ink/60">Today</dt><dd>{selected.properties.slot ?? selected.properties.booking ?? "not booked"}</dd>
                  </dl>
                </div>
              ) : (
                <p className="text-mist">Tap a plot: who farms it, the crop, and what its FAO-56 water balance needs today.</p>
              )}
            </div>
          </div>
        </section>

        {/* Energy: where the sun is going right now */}
        <section aria-label="Energy now" className="flex min-w-0 flex-col rounded-[20px] border border-soil bg-night-2 p-4">
          <div className="flex items-baseline justify-between gap-2">
            <h2 className="text-[18px] font-semibold text-ink">Where the sun is going</h2>
            <span className="num text-[12px] text-mist">drive telemetry, 20 s steps</span>
          </div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-[44px] leading-none text-sun-ink md:text-[56px]"><Roll value={pv.toFixed(2)} /></span>
            <span className="text-sm text-mist">kW of sun</span>
          </div>
          <div className="mt-2 flex-1 overflow-x-auto" role="region" tabIndex={0} aria-label="Energy flow diagram">
            <div className="min-w-[520px]">
            <EnergyFlow pvKw={pv} pumpKw={tel?.power_kw ?? 0} flowM3h={tel?.flow_m3h_true ?? 0}
              activeLoad={cur?.action === "mill" ? "mill" : cur?.action === "chaff" ? "chaff" : null}
              loadKw={loadKw} batteryKw={batKw} driveState={tel?.state ?? "–"} fault={tel?.fault ?? null} />
            </div>
          </div>
        </section>

        {/* Instrument strip */}
        <section aria-label="Today in numbers" className="grid min-w-0 grid-cols-2 divide-soil border-y border-soil sm:grid-cols-3 sm:divide-x lg:grid-cols-4 xl:col-span-2">
          <Readout label="Water planned, rest of day" value={fmt.n(snap?.summary.water_m3_p50, 0)} unit="m³" tone="text-water-ink" sub="middle of the forecast (P50)" />
          <Readout label="Verified today" value={fmt.n(today.m3, 0)} unit="m³" tone="text-ink" sub={`${today.n} receipts on the ledger`} />
          <Readout label="Diesel avoided today" value={fmt.n(today.diesel, 1)} unit="L" sub="vs a 5 HP diesel pump" />
          <div className="col-span-2 min-w-0 px-4 py-3 sm:col-span-1">
            <div className="flex items-center gap-2 text-[12px] text-mist">Groundwater, zaid season <SourceTag kind="assumption" /></div>
            <div className="num mt-1.5 text-[28px] leading-none md:text-[34px]"><Roll value={fmt.pct(zaidUsed / zaidCap, 0)} /></div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-night-3" role="meter" aria-valuemin={0} aria-valuemax={zaidCap} aria-valuenow={zaidUsed} aria-label="Season budget used">
              <div className="h-full rounded-full bg-water transition-[width] duration-500" style={{ width: `${Math.min(100, (zaidUsed / zaidCap) * 100)}%` }} />
            </div>
            <div className="num mt-1 text-[12px] text-mist">{fmt.n(zaidUsed, 0)} of {fmt.n(zaidCap, 0)} m³, hard cap</div>
          </div>
        </section>

        {/* Log */}
        <details className="min-w-0 xl:col-span-2">
          <summary className="cursor-pointer py-1 text-[18px] font-semibold">What happened today <span className="text-[14px] text-mist">({feed.length})</span></summary>
          <ol className="num flex mt-2 max-h-64 flex-col overflow-y-auto border-l border-soil text-[14px]" aria-live="polite" tabIndex={0}>
            {feed.length === 0 && <li className="pl-4 text-mist">The day has not started. Click the day bar above, or press Jump to 13:45.</li>}
            {feed.map((f, i) => (
              <li key={i} className="relative flex gap-3 py-1 pl-4">
                <span className={`absolute -left-[4px] top-[9px] h-[7px] w-[7px] rounded-full ${f.kind === "nowcast" || f.kind === "callback" ? "bg-water" : f.kind === "receipt" ? "bg-sun" : f.text.startsWith("Drive fault") ? "bg-fault" : "bg-soil"}`} aria-hidden />
                <span className="shrink-0 text-mist">{f.ts}</span>
                <span className={f.kind === "nowcast" ? "text-water-ink" : "text-fog"}>{f.text}</span>
              </li>
            ))}
          </ol>
        </details>
      </div>
    </Shell>
  );
}
