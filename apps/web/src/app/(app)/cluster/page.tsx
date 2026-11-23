"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Shell } from "@/components/Shell";
import { Btn, ErrorNote, Panel, SourceTag, Stat } from "@/components/ui";
import { fmt, getJSON, OPERATOR_TOKEN, postJSON, useApi } from "@/lib/api";

type Health = { pump_id: string; status: "live" | "late" | "silent" | "stalled" | "never"; last_seen: string | null; minutes_since: number | null; reason_en: string; reason_hi: string; alert: boolean; source: string };
type Quality = { borewell: string; ec_dsm: number; tds_mg_l: number; restriction: "none" | "slight_moderate" | "severe"; label_en: string; label_hi: string; crops_ok: string[]; crops_at_risk: string[]; source: string };
type Pump = { pump_id: string; name: string; kwp: number; lon: number; lat: number; operator: string; plots: number; bookings_today: number; water_m3_p50: number; requested_m3: number; short_today: { booking_id: string; need_m3: number; expected_today_m3: number }[]; fault: string | null; live: boolean; health: Health; water_quality: Quality };
type Cluster = { day: string; clock: string; pumps: Pump[]; transmitting: number; context: { value: number; note: string } };
type Suggest = { pump_id: string; fault: string | null; suggestions: { booking_id: string; need_m3: number; expected_here_m3: number; to_pump: string; distance_m: number; expected_today_m3: number; slots: string | null }[] };
type Recharge = { extraction_m3_per_year: number; target_m3_per_year: number; period: string; cheapest: string | null; options: { kind: string; name_en: string; name_hi: string; m3_per_year_each: number; cost_rs_each: number; count: number; total_m3_per_year: number; total_cost_rs: number; rs_per_m3_year: number; source_kind: string }[] };
type Village = { plots: { features: { geometry: { coordinates: number[][][] }; properties: { plot_id: string; pump_id: string; crop: string; booking: string | null } }[] } };
type Bounds = { west: number; south: number; east: number; north: number };

const HEALTH: Record<Health["status"], { cls: string; en: string; hi: string }> = {
  live: { cls: "bg-leaf", en: "Reporting", hi: "डेटा आ रहा है" },
  late: { cls: "bg-sun", en: "Late", hi: "देर से" },
  silent: { cls: "bg-fault", en: "Silent", hi: "बंद" },
  stalled: { cls: "bg-fault", en: "Stalled", hi: "रुका" },
  never: { cls: "bg-mist", en: "Never reported", hi: "कभी नहीं" },
};
const QUAL: Record<Quality["restriction"], string> = { none: "text-leaf", slight_moderate: "text-sun", severe: "text-fault" };
const PUMP_COLOR: Record<string, string> = { P1: "#F2B33D", P2: "#5FB3E6", P3: "#9BC46A" };

function SiteMap({ pumps, village, bounds, layer }: { pumps: Pump[]; village: Village | null; bounds: Bounds | null; layer: "true" | "crops" }) {
  const W = 1000;
  const H = 1000;
  const x = (lon: number) => ((lon - (bounds?.west ?? 0)) / ((bounds?.east ?? 1) - (bounds?.west ?? 0))) * W;
  const y = (lat: number) => (((bounds?.north ?? 1) - lat) / ((bounds?.north ?? 1) - (bounds?.south ?? 0))) * H;
  if (!bounds) return <div className="aspect-square w-full animate-pulse rounded-lg bg-night" />;
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="aspect-square w-full rounded-lg bg-night" role="img" aria-label="Sentinel-2 image of the site with the three pumps and their plots">
        <image href="/basemap/samastipur_s2_truecolor.png" x={0} y={0} width={W} height={H} preserveAspectRatio="none" opacity={layer === "true" ? 0.9 : 0.45} />
        {layer === "crops" && <image href="/basemap/samastipur_s2_crops.png" x={0} y={0} width={W} height={H} preserveAspectRatio="none" opacity={0.9} />}
        {village?.plots.features.map((f) => {
          const ring = f.geometry.coordinates[0];
          const d = ring.map(([lo, la], i) => `${i ? "L" : "M"}${x(lo).toFixed(1)},${y(la).toFixed(1)}`).join("") + "Z";
          return <path key={f.properties.plot_id} d={d} fill={PUMP_COLOR[f.properties.pump_id] ?? "#fff"} fillOpacity={f.properties.booking ? 0.75 : 0.28} stroke="#0b1110" strokeWidth={1.2} />;
        })}
        {pumps.map((p) => (
          <g key={p.pump_id} transform={`translate(${x(p.lon)},${y(p.lat)})`}>
            <circle r={70} fill="none" stroke={PUMP_COLOR[p.pump_id]} strokeOpacity={0.5} strokeDasharray="6 8" strokeWidth={2} />
            <circle r={16} fill={p.health.alert ? "#E5484D" : PUMP_COLOR[p.pump_id]} stroke="#0b1110" strokeWidth={4} />
            <text y={-26} textAnchor="middle" className="fill-white text-[30px] font-semibold" style={{ paintOrder: "stroke", stroke: "#0b1110", strokeWidth: 6 }}>{p.pump_id}</text>
          </g>
        ))}
      </svg>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-mist">
        <SourceTag kind="real" /> Sentinel-2 L2A, 26 Jan 2025, 10 m
        <SourceTag kind="simulated" /> pumps and plots placed on the image
      </div>
    </div>
  );
}

export default function ClusterPage() {
  const { data, error, reload } = useApi<Cluster>("/api/cluster", 5000);
  const { data: village } = useApi<Village>("/api/village?pump=all");
  const { data: bounds } = useApi<Bounds>("/basemap/samastipur_s2_truecolor.json");
  const { data: recharge } = useApi<Recharge>("/api/cluster/recharge");
  const [layer, setLayer] = useState<"true" | "crops">("true");
  const [sugg, setSugg] = useState<Suggest | null>(null);
  const [pending, setPending] = useState<Suggest["suggestions"][number] | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const totals = useMemo(() => {
    const ps = data?.pumps ?? [];
    return { water: ps.reduce((a, p) => a + p.water_m3_p50, 0), req: ps.reduce((a, p) => a + p.requested_m3, 0) };
  }, [data]);

  const suggest = async (pid: string) => {
    setBusy(true);
    setErr(null);
    try {
      const r = await getJSON<Suggest>(`/api/cluster/suggest?pump=${pid}`);
      setSugg(r);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };
  const move = async () => {
    if (!pending) return;
    setBusy(true);
    try {
      const r = await postJSON<{ booking_id: string; to_pump: string; slot_start: string | null; slot_end: string | null; expected_today_m3: number; unlock_code: string | null }>(
        "/api/tools/transfer_booking", { args: { booking_id: pending.booking_id, to_pump: pending.to_pump }, confirm: true }, OPERATOR_TOKEN);
      setDone(`${r.booking_id} → ${r.to_pump}, ${r.slot_start ?? "–"}–${r.slot_end ?? "–"}, ~${fmt.n(r.expected_today_m3)} m³ today${r.unlock_code ? `, new code ${r.unlock_code}` : ""}`);
      setSugg(null);
      reload();
    } catch (e) {
      setErr(String(e));
    } finally {
      setPending(null);
      setBusy(false);
    }
  };

  return (
    <Shell title="Pump cluster">
      <ErrorNote error={error || err} />
      <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <Panel className="xl:sticky xl:top-4 xl:self-start" title="Three pumps, one sky" right={
          <div className="flex gap-1" role="group" aria-label="Map layer">
            <Btn tone={layer === "true" ? "sun" : "ghost"} onClick={() => setLayer("true")}>Satellite</Btn>
            <Btn tone={layer === "crops" ? "sun" : "ghost"} onClick={() => setLayer("crops")}>Crop seasons</Btn>
          </div>}>
          <SiteMap pumps={data?.pumps ?? []} village={village} bounds={bounds} layer={layer} />
          {layer === "crops" && (
            <p className="mt-2 text-[12px] text-mist">Classes from 30 clear Sentinel-2 dates (Jun 2024–May 2025) by NDVI phenology; seasons, not species, and not checked against field labels. This point sits on Samastipur town, so most of the image is built-up.</p>
          )}
        </Panel>

        <div className="flex min-w-0 flex-col gap-4">
          <Panel>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <Stat label="Pumps reporting" value={`${data?.transmitting ?? "–"}/${data?.pumps.length ?? "–"}`} tone={data && data.transmitting < data.pumps.length ? "fault" : "leaf"} />
              <Stat label="Planned today" value={fmt.n(totals.water)} unit="m³" tone="water" source="simulated" />
              <Stat label="Asked for" value={fmt.n(totals.req)} unit="m³" />
              <Stat label="Clock" value={data?.clock ?? "–"} sub={data?.day} />
            </div>
            <p className="mt-3 text-[12px] text-mist">Why watch for silence: on one state portal only {fmt.pct(data?.context.value)} of pumps that ever reported were still transmitting ({data?.context.note}).</p>
          </Panel>

          {data?.pumps.map((p) => (
            <Panel key={p.pump_id} title={<span className="flex items-center gap-2"><span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: PUMP_COLOR[p.pump_id] }} />{p.name}</span>}
              right={<Link href={`/passport/${p.pump_id}`} className="text-[12px] text-sun underline-offset-2 hover:underline">Pump Passport →</Link>}>
              <div className="grid gap-4 md:grid-cols-3">
                <div className="flex flex-col gap-1">
                  <div className="flex items-center gap-2 text-[12px] text-mist">Data health</div>
                  <div className="flex items-center gap-2">
                    <span className={`h-2.5 w-2.5 rounded-full ${HEALTH[p.health.status].cls} ${p.health.status === "live" ? "motion-safe:animate-pulse" : ""}`} aria-hidden />
                    <span className={`text-lg ${p.health.alert ? "text-fault" : "text-white"}`}>{HEALTH[p.health.status].en}</span>
                    <span className="text-[13px] text-mist" lang="hi">{HEALTH[p.health.status].hi}</span>
                  </div>
                  <div className="text-[12px] text-mist">{p.health.reason_en}</div>
                  <div className="text-[11px] text-mist/80">{p.health.source}</div>
                </div>
                <div className="flex flex-col gap-1">
                  <div className="flex items-center gap-2 text-[12px] text-mist">Today <SourceTag kind="simulated" /></div>
                  <div className="num text-lg text-water">{fmt.n(p.water_m3_p50)} <span className="text-[13px] text-mist">of {fmt.n(p.requested_m3)} m³</span></div>
                  <div className="text-[12px] text-mist">{p.bookings_today} bookings · {p.plots} plots{p.fault ? <span className="text-fault"> · fault {p.fault}</span> : null}</div>
                  {p.short_today.length > 0 && <div className="text-[12px] text-sun">{p.short_today.length} bookings short today</div>}
                </div>
                <div className="flex flex-col gap-1">
                  <div className="flex items-center gap-2 text-[12px] text-mist">Borewell water <SourceTag kind="simulated" /></div>
                  <div className={`num text-lg ${QUAL[p.water_quality.restriction]}`}>{p.water_quality.ec_dsm} <span className="text-[13px] text-mist">dS/m · {p.water_quality.tds_mg_l} mg/l</span></div>
                  <div className="text-[12px] text-mist">{p.water_quality.label_en}</div>
                  <div className="text-[12px] text-mist" lang="hi">{p.water_quality.label_hi}</div>
                </div>
              </div>
              {(p.short_today.length > 0 || p.fault) && (
                <div className="mt-3 border-t border-soil pt-3">
                  <Btn tone="sun" onClick={() => suggest(p.pump_id)} disabled={busy}>{busy && sugg === null ? "Checking neighbours…" : "Find a neighbouring pump"}</Btn>
                </div>
              )}
            </Panel>
          ))}

          {sugg && (
            <Panel title={`Transfers from ${sugg.pump_id}`} right={<span className="text-[11px] text-mist">within {700} m of field channel · needs confirmation</span>}>
              {sugg.suggestions.length === 0 ? <p className="text-[13px] text-mist">No reachable pump has spare sun for these bookings today.</p> : (
                <ul className="flex flex-col gap-2">
                  {sugg.suggestions.map((s) => (
                    <li key={s.booking_id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-night px-3 py-2">
                      <span className="num text-[13px]">{s.booking_id} · needs {fmt.n(s.need_m3)} m³ · here ~{fmt.n(s.expected_here_m3)}</span>
                      <span className="num text-[13px] text-water">{s.to_pump} ({fmt.n(s.distance_m)} m): ~{fmt.n(s.expected_today_m3)} m³ {s.slots ?? ""}</span>
                      <Btn tone="sun" onClick={() => setPending(s)}>Move</Btn>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          )}
          {done && <p role="status" className="rounded-lg border border-leaf/40 bg-leaf/10 px-3 py-2 text-[13px] text-leaf">Moved: {done}</p>}

          {recharge && (
            <Panel title="Recharge pairing" right={<span className="text-[11px] text-mist">{recharge.period}</span>}>
              <p className="text-[13px] text-mist">The cluster drew <span className="num text-white">{fmt.n(recharge.extraction_m3_per_year)} m³</span> of groundwater in the last year (drive-metered receipts). To put it back:</p>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                {recharge.options.map((o) => (
                  <div key={o.kind} className={`rounded-lg border p-3 ${recharge.cheapest === o.kind ? "border-water/60" : "border-soil"}`}>
                    <div className="flex items-center justify-between gap-2"><span className="text-white">{o.name_en}</span><SourceTag kind={o.source_kind.startsWith("published") ? "published" : "assumption"} /></div>
                    <div className="text-[12px] text-mist" lang="hi">{o.name_hi}</div>
                    <div className="num mt-2 text-2xl text-water">{o.count} <span className="text-[13px] text-mist">× {fmt.n(o.m3_per_year_each)} m³/yr</span></div>
                    <div className="num text-[13px] text-mist">{fmt.rs(o.total_cost_rs)} · {fmt.rs(o.rs_per_m3_year, 1)} per m³ of yearly recharge</div>
                  </div>
                ))}
              </div>
              <p className="mt-2 text-[11px] text-mist">The shaft figure is a CGWB planning norm from a Rajasthan block plan; confirm a Bihar value before funding.</p>
            </Panel>
          )}
        </div>
      </div>

      {pending && (
        <div role="dialog" aria-modal="true" aria-labelledby="mv-t" className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-md rounded-xl border border-soil bg-night-2 p-5">
            <h2 id="mv-t" className="text-lg text-white">Move {pending.booking_id} to {pending.to_pump}?</h2>
            <p className="mt-2 text-[13px] text-mist">The farmer is told the new time and gets a new unlock code; the code for the old pump stops working.</p>
            <div className="mt-4 flex justify-end gap-2">
              <Btn tone="ghost" onClick={() => setPending(null)}>Keep it</Btn>
              <Btn tone="sun" onClick={move} disabled={busy}>Confirm move</Btn>
            </div>
          </div>
        </div>
      )}
    </Shell>
  );
}
