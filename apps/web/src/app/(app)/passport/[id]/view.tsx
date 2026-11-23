"use client";

import Link from "next/link";
import { Shell } from "@/components/Shell";
import { ErrorNote, Panel, SourceTag, Stat } from "@/components/ui";
import { fmt, useApi } from "@/lib/api";

type Passport = {
  pump: { pump_id: string; name: string; kwp: number; operator: string };
  as_of: string; period_days: number; receipts: number; days_with_receipts: number;
  utilisation_kwh_per_kwp_yr: number; energy_kwh: number; water_m3: number; farmers_served: number;
  tenant_water_share: number | null; revenue_rs: number; revenue_by_kind_rs: Record<string, number>;
  monthly_revenue_rs: Record<string, number>; monthly_by_kind_rs: Record<string, Record<string, number>>; uptime: number | null; faults: { code: string; count: number }[];
  fault_log: { code: string; at: string; downtime_h: number }[]; downtime_h: number;
  repayment_on_time: number | null; after_harvest_credits: number; ledger_verified: boolean; data_health: string;
  score: { value: number; grade: string; weights: Record<string, number>; parts: Record<string, number>; note: string };
  water_quality: { ec_dsm: number; tds_mg_l: number; label_en: string; restriction: string };
};

const KIND: Record<string, { label: string; cls: string }> = {
  water: { label: "Water", cls: "bg-water" }, mill: { label: "Flour mill", cls: "bg-sun" },
  chaff: { label: "Chaff cutter", cls: "bg-[#c98b4a]" }, battery: { label: "Battery packs", cls: "bg-mist" },
};
const PART_LABEL: Record<string, string> = {
  utilisation: "Sun put to work (vs 1,000 kWh/kWp/yr)", uptime: "Uptime", repayment: "After-harvest repaid on time",
  revenue_stability: "Revenue steadiness (1 − month-to-month CV)", data: "Ledger verified + still reporting",
};

function ScoreBar({ value, grade }: { value: number; grade: string }) {
  return (
    <div className="w-full" role="img" aria-label={`Scorecard ${value} of 100, grade ${grade}`}>
      <div className="flex items-baseline justify-between">
        <span className="num text-7xl leading-none text-ink">{value}<span className="ml-1 text-base text-ink/55">/ 100</span></span>
        <span className="stamp-in num rotate-[-6deg] rounded-md border-[3px] border-[#a8361f] px-3 py-1 text-3xl font-bold text-[#a8361f]" aria-hidden>{grade}</span>
      </div>
      <div className="relative mt-4 h-3 rounded-full bg-ink/10">
        <div className="h-3 rounded-full bg-[#c98b1a] motion-safe:transition-[width] motion-safe:duration-1000" style={{ width: `${value}%` }} />
        {[50, 65, 80].map((x) => <span key={x} className="absolute top-[-3px] h-[18px] w-px bg-ink/40" style={{ left: `${x}%` }} aria-hidden />)}
      </div>
      <div className="num mt-1 flex justify-between text-[10px] text-ink/55"><span>0</span><span style={{ marginLeft: "40%" }}>C</span><span>B</span><span>A</span><span>100</span></div>
    </div>
  );
}

export default function PassportView({ id }: { id: string }) {
  const { data: p, error } = useApi<Passport>(`/api/pumps/${id}/passport`);
  const months = p ? Object.entries(p.monthly_revenue_rs) : [];
  const maxM = Math.max(1, ...months.map(([, v]) => v));
  const kinds = p ? Object.entries(p.revenue_by_kind_rs).sort((a, b) => b[1] - a[1]) : [];

  return (
    <Shell title="Pump Passport">
      <ErrorNote error={error} />
      <div className="mb-4 flex flex-wrap items-center gap-3 text-[13px]">
        {["P1", "P2", "P3"].map((x) => (
          <Link key={x} href={`/passport/${x}`} aria-current={x === id ? "page" : undefined}
            className={`rounded-full px-3 py-1 ${x === id ? "bg-sun text-ink" : "bg-night-2 text-fog hover:text-white"}`}>{x}</Link>
        ))}
        <Link href="/cluster" className="text-mist underline-offset-2 hover:underline">← cluster</Link>
        <a href={`/api/pumps/${id}/passport.pdf`} className="ml-auto rounded-lg border border-soil px-3 py-1.5 text-fog hover:border-sun hover:text-white">Download one-page PDF</a>
      </div>
      {!p ? <div className="h-64 animate-pulse rounded-xl bg-night-2" /> : (
        <div className="grid min-w-0 gap-8 xl:grid-cols-[minmax(0,4fr)_minmax(0,7fr)]">
          <article className="paper perforated relative min-w-0 rounded-b-lg px-6 pb-6 pt-7 text-ink shadow-[0_24px_50px_-20px_rgba(0,0,0,.7)] xl:sticky xl:top-28 xl:self-start" aria-label={`Pump Passport ${p.pump.pump_id}`}>
            <div className="flex items-baseline justify-between gap-3 border-b border-ink/15 pb-3">
              <div>
                <div className="font-serif text-2xl italic">Pump Passport</div>
                <div className="num text-[12px] text-ink/60">{p.pump.pump_id} · {p.pump.name}</div>
              </div>
              <span className="num rounded border border-ink/25 px-1.5 text-[10px] tracking-wider text-ink/60">SIMULATED</span>
            </div>
            <div className="mt-5">
            <div className="flex flex-col gap-3">
              <ScoreBar value={p.score.value} grade={p.score.grade} />
              <p className="text-[12px] text-ink/65">{p.score.note}</p>
            </div>
            <ul className="mt-4 flex flex-col gap-2">
              {Object.entries(p.score.parts).map(([k, v]) => (
                <li key={k}>
                  <div className="flex justify-between text-[12px]"><span>{PART_LABEL[k] ?? k}</span><span className="num text-ink/60">{p.score.weights[k]} pts · {fmt.pct(v)}</span></div>
                  <div className="mt-1 h-1.5 rounded-full bg-ink/10"><div className="h-1.5 rounded-full bg-[#c98b1a]" style={{ width: `${Math.min(v, 1) * 100}%` }} /></div>
                </li>
              ))}
            </ul>
            <dl className="mt-5 grid grid-cols-2 gap-y-1 border-t border-dashed border-ink/25 pt-3 text-[12px]">
              <dt className="text-ink/60">Operator</dt><dd className="text-right">{p.pump.operator}</dd>
              <dt className="text-ink/60">Array</dt><dd className="num text-right">{p.pump.kwp} kWp</dd>
              <dt className="text-ink/60">Ledger</dt><dd className={`text-right ${p.ledger_verified ? "text-[#1d8a37]" : "text-fault"}`}>{p.ledger_verified ? "hash chain verified" : "NOT verified"}</dd>
              <dt className="text-ink/60">Data health</dt><dd className="text-right">{p.data_health}</dd>
              <dt className="text-ink/60">Borewell</dt><dd className="num text-right">{p.water_quality.ec_dsm} dS/m · {p.water_quality.label_en}</dd>
            </dl>
            </div>
          </article>

          <div className="flex min-w-0 flex-col gap-4">
            <Panel title={`Last ${p.period_days} days to ${p.as_of}`}>
              <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                <Stat label="Sun put to work" value={fmt.n(p.utilisation_kwh_per_kwp_yr)} unit="kWh/kWp/yr" tone="sun" />
                <Stat label="Water delivered" value={fmt.n(p.water_m3)} unit="m³" tone="water" sub={`${p.farmers_served} farmers`} />
                <Stat label="To tenants" value={fmt.pct(p.tenant_water_share)} sub="share of water" />
                <Stat label="Revenue" value={fmt.rs(p.revenue_rs)} sub={`${fmt.n(p.receipts)} receipts`} />
                <Stat label="Uptime" value={fmt.pct(p.uptime, 1)} sub={`${fmt.n(p.downtime_h, 1)} h down`} />
                <Stat label="Faults" value={p.faults.reduce((a, f) => a + f.count, 0)} sub={p.faults.map((f) => `${f.code}×${f.count}`).join(" ") || "none"} />
                <Stat label="Repaid on time" value={fmt.pct(p.repayment_on_time)} sub={`${p.after_harvest_credits} after-harvest credits`} />
                <Stat label="Energy" value={fmt.n(p.energy_kwh)} unit="kWh" />
              </div>
            </Panel>
            <Panel title="Revenue by month" right={<span className="text-[11px] text-mist">from receipts</span>}>
              <div className="flex h-40 items-end gap-1" role="img" aria-label="Monthly revenue bars">
                {months.map(([m, v]) => (
                  <div key={m} className="flex min-w-0 flex-1 flex-col items-center gap-1" title={`${m}: ₹${v}`}>
                    <div className="flex w-full flex-col-reverse overflow-hidden rounded-t" style={{ height: `${(v / maxM) * 120}px` }}>
                      {Object.keys(KIND).map((k) => {
                        const x = p.monthly_by_kind_rs?.[m]?.[k] ?? 0;
                        return x > 0 ? <div key={k} className={KIND[k].cls} style={{ height: `${(x / v) * 100}%` }} /> : null;
                      })}
                    </div>
                    <span className="num text-[10px] text-mist">{m.slice(5)}</span>
                  </div>
                ))}
              </div>
              <div className="mt-3 flex flex-wrap gap-3 text-[12px]">
                {kinds.map(([k, v]) => (
                  <span key={k} className="flex items-center gap-1.5 text-fog"><span className={`h-2 w-2 rounded-full ${KIND[k]?.cls ?? "bg-mist"}`} />{KIND[k]?.label ?? k} {fmt.rs(v)}</span>
                ))}
              </div>
            </Panel>
            <Panel title="Fault log" right={<SourceTag kind="simulated" />}>
              {p.fault_log.length === 0 ? <p className="text-[13px] text-mist">No faults logged.</p> : (
                <table className="w-full text-[13px]">
                  <thead><tr className="text-left text-mist"><th className="py-1 font-normal">Date</th><th className="font-normal">Code</th><th className="text-right font-normal">Downtime</th></tr></thead>
                  <tbody>{p.fault_log.map((f, i) => (
                    <tr key={i} className="border-t border-soil"><td className="num py-1.5 text-fog">{f.at}</td><td className="num text-white">{f.code}</td><td className="num text-right text-fog">{f.downtime_h} h</td></tr>
                  ))}</tbody>
                </table>
              )}
            </Panel>
          </div>
        </div>
      )}
    </Shell>
  );
}
