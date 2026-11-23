"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { BandChart, BandLegend } from "@/components/BandChart";
import { EnergyFlow } from "@/components/EnergyFlow";
import { CropLegend, type PlotFeature, PlotMosaic } from "@/components/PlotMosaic";
import { Shell } from "@/components/Shell";
import { ErrorNote, Panel, SourceTag, Stat } from "@/components/ui";
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
    const push = (text: string) => setFeed((f) => [{ ts: String(e.ts).slice(11, 16), kind: e.kind, text }, ...f].slice(0, 30));
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

  return (
    <Shell title="Village Twin">
      <ErrorNote error={error} />
      <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          <Panel
            title={<span className="flex items-center gap-2">Command area, pump P1 (schematic) <SourceTag kind="simulated" /></span>}
            right={<span className="text-[11px] text-mist">{village ? `${village.plots.features.length} plots` : ""}</span>}
          >
            <div className="grid min-w-0 gap-4 md:grid-cols-[minmax(0,1fr)_220px]">
              <div className="relative">
                {village ? (
                  <PlotMosaic
                    features={village.plots.features}
                    pump={village.pumps[0]}
                    sellers={village.sellers}
                    activeFarmer={activeFarmerId}
                    selected={selected?.properties.plot_id}
                    onSelect={setSelected}
                    cloud={!!snap?.cloud_applied && now >= 15 && now <= 20}
                  />
                ) : (
                  <div className="aspect-square animate-pulse rounded bg-night-3" />
                )}
              </div>
              <div className="flex flex-col gap-3 text-[13px]">
                <CropLegend />
                {selected ? (
                  <div className="rounded-md border border-soil p-3" aria-live="polite">
                    <div className="font-medium">{selected.properties.farmer}</div>
                    <div className="text-mist">
                      {selected.properties.tenant ? "Tenant" : selected.properties.owner ? "Pump owner" : "Landholder"} ·{" "}
                      {selected.properties.language}
                    </div>
                    <dl className="num mt-2 grid grid-cols-2 gap-y-1 text-[12px]">
                      <dt className="text-mist">Crop</dt>
                      <dd>{selected.properties.crop} ({selected.properties.stage})</dd>
                      <dt className="text-mist">Area</dt>
                      <dd>{selected.properties.area_ha.toFixed(2)} ha</dd>
                      <dt className="text-mist">FAO-56 need</dt>
                      <dd>{selected.properties.need_m3.toFixed(0)} m³</dd>
                      <dt className="text-mist">Today</dt>
                      <dd>{selected.properties.slot ?? selected.properties.booking ?? "not booked"}</dd>
                    </dl>
                  </div>
                ) : (
                  <p className="text-mist">Select a plot to see who farms it and what its crop needs.</p>
                )}
              </div>
            </div>
          </Panel>
          <Panel title="Sun today: forecast band and what actually happened" right={<SourceTag kind="real" />}>
            <div className="min-h-[180px]">
            {snap && (
              <BandChart
                labels={snap.forecast.labels}
                q10={snap.forecast.q10}
                q50={snap.forecast.q50}
                q90={snap.forecast.q90}
                actual={snap.forecast.actual}
                actualUpTo={now}
                nowIndex={now}
                height={230}
              />
            )}
            </div>
            <div className="mt-2">
              <BandLegend />
            </div>
          </Panel>
        </div>
        <div className="flex min-w-0 flex-col gap-4">
          <Panel title="Energy now" right={<span className="text-[11px] text-mist">telemetry every 20 s of simulated time</span>}>
            <EnergyFlow
              pvKw={pv}
              pumpKw={tel?.power_kw ?? 0}
              flowM3h={tel?.flow_m3h_true ?? 0}
              activeLoad={cur?.action === "mill" ? "mill" : cur?.action === "chaff" ? "chaff" : null}
              loadKw={loadKw}
              batteryKw={batKw}
              driveState={tel?.state ?? "–"}
              fault={tel?.fault ?? null}
            />
          </Panel>
          <div className="grid grid-cols-2 gap-4">
            <Panel title="Plan, rest of today (P50)">
              <div className="grid gap-3">
                <Stat value={fmt.n(snap?.summary.water_m3_p50, 0)} unit="m³" label="Water" tone="water" />
                <Stat value={fmt.n((snap?.summary.mill_kwh_p50 ?? 0) + (snap?.summary.chaff_kwh_p50 ?? 0) + (snap?.summary.battery_kwh_p50 ?? 0), 1)} unit="kWh" label="Mill, cutter, batteries" tone="sun" />
              </div>
            </Panel>
            <Panel title="Verified today">
              <div className="grid gap-3">
                <Stat value={fmt.n(today.m3, 0)} unit="m³" label={`Solar water, ${today.n} receipts`} tone="water" />
                <Stat value={fmt.n(today.diesel, 1)} unit="L" label="Diesel avoided" tone="sun" />
              </div>
            </Panel>
          </div>
          <Panel title="Groundwater budget (zaid season)" right={<SourceTag kind="assumption" />}>
            <div className="num flex items-baseline justify-between text-sm">
              <span>{fmt.n(zaidUsed, 0)} m³ used</span>
              <span className="text-mist">of {fmt.n(zaidCap, 0)} m³</span>
            </div>
            <div className="mt-2 h-2.5 overflow-hidden rounded-full bg-night-3" role="meter" aria-valuemin={0} aria-valuemax={zaidCap} aria-valuenow={zaidUsed} aria-label="Season budget used">
              <div className="h-full rounded-full bg-water transition-[width] duration-500" style={{ width: `${Math.min(100, (zaidUsed / zaidCap) * 100)}%` }} />
            </div>
            <p className="mt-2 text-[12px] text-mist">Hard cap enforced by the planner and the edge controller. Block category UNVERIFIED.</p>
          </Panel>
          <Panel title="Live feed">
            <ol className="flex max-h-64 flex-col gap-1.5 overflow-y-auto text-[12.5px]" aria-live="polite">
              {feed.length === 0 && <li className="text-mist">Press “Play day” or “Jump to 13:45” to run the day.</li>}
              {feed.map((f, i) => (
                <li key={i} className="flex gap-2">
                  <span className="num shrink-0 text-mist">{f.ts}</span>
                  <span className={f.kind === "nowcast" ? "text-water" : f.kind === "receipt" ? "text-fog" : "text-fog"}>{f.text}</span>
                </li>
              ))}
            </ol>
          </Panel>
        </div>
      </div>
    </Shell>
  );
}
