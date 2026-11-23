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
  monthly_revenue_rs: Record<string, number>; uptime: number | null; faults: { code: string; count: number }[];
  fault_log: { code: string; at: string; downtime_h: number }[]; downtime_h: number;
  repayment_on_time: number | null; after_harvest_credits: number; ledger_verified: boolean; data_health: string;
  score: { value: number; grade: string; weights: Record<string, number>; parts: Record<string, number>; note: string };
  water_quality: { ec_dsm: number; tds_mg_l: number; label_en: string; restriction: string };
};

const KIND: Record<string, { label: string; cls: string }> = {
  water: { label: "Water", cls: "bg-water" }, mill: { label: "Flour mill", cls: "bg-sun" },
  chaff: { label: "Chaff cutter", cls: "bg-[#c98b4a]" }, battery: { label: "Battery packs", cls: "bg-leaf" },
};
const PART_LABEL: Record<string, string> = {
  utilisation: "Sun put to work (vs 1,000 kWh/kWp/yr)", uptime: "Uptime", repayment: "After-harvest repaid on time",
  revenue_stability: "Revenue steadiness (1 − month-to-month CV)", data: "Ledger verified + still reporting",
};

function Gauge({ value, grade }: { value: number; grade: string }) {
  const r = 70;
  const c = Math.PI * r;
  const off = c * (1 - value / 100);
  return (
    <svg viewBox="0 0 180 110" className="w-full max-w-[260px]" role="img" aria-label={`Scorecard ${value} of 100, grade ${grade}`}>
      <path d="M20 95 A70 70 0 0 1 160 95" fill="none" stroke="#2a3430" strokeWidth={14} strokeLinecap="round" />
      <path d="M20 95 A70 70 0 0 1 160 95" fill="none" stroke="#F2B33D" strokeWidth={14} strokeLinecap="round"
        strokeDasharray={c} strokeDashoffset={off} className="motion-safe:transition-[stroke-dashoffset] motion-safe:duration-1000" />
      <text x="90" y="82" textAnchor="middle" className="fill-white num text-[34px]">{value}</text>
      <text x="90" y="104" textAnchor="middle" className="fill-[#9aa7a0] text-[12px]">grade {grade}</text>
    </svg>
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
        <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,4fr)_minmax(0,7fr)]">
          <Panel title={p.pump.name} right={<SourceTag kind="simulated" />}>
            <div className="flex flex-col items-center gap-2">
              <Gauge value={p.score.value} grade={p.score.grade} />
              <p className="text-center text-[12px] text-mist">{p.score.note}</p>
            </div>
            <ul className="mt-4 flex flex-col gap-2">
              {Object.entries(p.score.parts).map(([k, v]) => (
                <li key={k}>
                  <div className="flex justify-between text-[12px]"><span className="text-fog">{PART_LABEL[k] ?? k}</span><span className="num text-mist">{p.score.weights[k]} pts · {fmt.pct(v)}</span></div>
                  <div className="mt-1 h-1.5 rounded-full bg-night"><div className="h-1.5 rounded-full bg-sun" style={{ width: `${Math.min(v, 1) * 100}%` }} /></div>
                </li>
              ))}
            </ul>
            <dl className="mt-4 grid grid-cols-2 gap-y-1 text-[12px]">
              <dt className="text-mist">Operator</dt><dd className="text-right text-fog">{p.pump.operator}</dd>
              <dt className="text-mist">Array</dt><dd className="num text-right text-fog">{p.pump.kwp} kWp</dd>
              <dt className="text-mist">Ledger</dt><dd className={`text-right ${p.ledger_verified ? "text-leaf" : "text-fault"}`}>{p.ledger_verified ? "hash chain verified" : "NOT verified"}</dd>
              <dt className="text-mist">Data health</dt><dd className="text-right text-fog">{p.data_health}</dd>
              <dt className="text-mist">Borewell</dt><dd className="num text-right text-fog">{p.water_quality.ec_dsm} dS/m · {p.water_quality.label_en}</dd>
            </dl>
          </Panel>

          <div className="flex min-w-0 flex-col gap-4">
            <Panel title={`Last ${p.period_days} days to ${p.as_of}`}>
              <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                <Stat label="Sun put to work" value={fmt.n(p.utilisation_kwh_per_kwp_yr)} unit="kWh/kWp/yr" tone="sun" />
                <Stat label="Water delivered" value={fmt.n(p.water_m3)} unit="m³" tone="water" sub={`${p.farmers_served} farmers`} />
                <Stat label="To tenants" value={fmt.pct(p.tenant_water_share)} sub="share of water" />
                <Stat label="Revenue" value={fmt.rs(p.revenue_rs)} tone="leaf" sub={`${fmt.n(p.receipts)} receipts`} />
                <Stat label="Uptime" value={fmt.pct(p.uptime, 1)} sub={`${fmt.n(p.downtime_h, 1)} h down`} />
                <Stat label="Faults" value={p.faults.reduce((a, f) => a + f.count, 0)} sub={p.faults.map((f) => `${f.code}×${f.count}`).join(" ") || "none"} />
                <Stat label="Repaid on time" value={fmt.pct(p.repayment_on_time)} sub={`${p.after_harvest_credits} after-harvest credits`} />
                <Stat label="Energy" value={fmt.n(p.energy_kwh)} unit="kWh" />
              </div>
            </Panel>
            <Panel title="Revenue by month" right={<span className="text-[11px] text-mist">from receipts</span>}>
              <div className="flex h-40 items-end gap-1" role="img" aria-label="Monthly revenue bars">
                {months.map(([m, v]) => (
                  <div key={m} className="flex min-w-0 flex-1 flex-col items-center gap-1">
                    <div className="w-full rounded-t bg-sun/80" style={{ height: `${(v / maxM) * 120}px` }} title={`${m}: ₹${v}`} />
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
