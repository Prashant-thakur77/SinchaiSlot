"use client";

import { useState } from "react";
import { Receipt } from "@/components/Receipt";
import { Shell } from "@/components/Shell";
import { Btn, ErrorNote, Roll, SourceTag } from "@/components/ui";
import { API, fmt, getJSON, useApi } from "@/lib/api";
import type { LedgerRow } from "@/lib/types";

type Summary = {
  receipts: number;
  m3: number;
  pump_kwh: number;
  secondary_kwh: number;
  diesel_l_avoided: number;
  co2_kg_avoided: number;
  farmers_served: number;
  tenant_farmers_served: number;
  water_revenue_rs: number;
  secondary_revenue_rs: number;
  merkle_root: string;
  first: string;
  last: string;
};
type Verify = { ok: boolean; first_bad_seq: number | null; checked: number; head?: string };
type Claim = { funder: string; period: string[]; totals: Summary; subsidy_equivalent_rs: number; status: string; method: Record<string, unknown> };
type Audit = { n_findings: number; findings: { receipt_id: string | null; rule: string; severity: string; detail: string }[] };

export default function LedgerPage() {
  const { data, error } = useApi<{ total: number; rows: LedgerRow[]; summary: Summary }>("/api/ledger?limit=60", 4000);
  const [verify, setVerify] = useState<Verify | null>(null);
  const [claim, setClaim] = useState<Claim | null>(null);
  const [audit, setAudit] = useState<Audit | null>(null);
  const [from, setFrom] = useState("2024-01-01");
  const [to, setTo] = useState("2024-03-31");
  const [scan, setScan] = useState<number | null>(null); // index of the receipt the scan line is on
  const s = data?.summary;
  const water = (data?.rows ?? []).filter((r) => r.kind === "water");
  const roll = water.slice(0, 8);

  const runVerify = async () => {
    setVerify(null);
    const result = getJSON<Verify>("/api/ledger/verify");
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!reduce) {
      for (let i = 0; i <= roll.length; i++) {
        setScan(i);
        await new Promise((r) => setTimeout(r, 170));
      }
    }
    setVerify(await result);
    setScan(null);
  };
  const stampFor = (i: number): "verified" | "pending" | "checking" =>
    scan === null ? (verify && !verify.ok ? "pending" : "verified") : i < scan ? "verified" : i === scan ? "checking" : "pending";

  return (
    <Shell title="Rasid ledger">
      <ErrorNote error={error} />
      <div className="grid min-w-0 gap-8 xl:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        {/* Left: the books */}
        <div className="flex min-w-0 flex-col gap-6 xl:sticky xl:top-28 xl:self-start">
          <div>
            <div className="text-[12px] text-mist">Solar water on receipts, each chained to the one before</div>
            <div className="num mt-2 text-[clamp(3.4rem,7vw,6.5rem)] leading-none text-water"><Roll value={fmt.n(s?.m3)} /><span className="ml-2 text-lg text-mist">m³</span></div>
            <div className="num mt-2 text-[12px] text-mist">{fmt.n(s?.receipts)} receipts · 3 pumps{s ? ` · ${s.first?.slice(0, 10)} to ${s.last?.slice(0, 10)}` : ""} <SourceTag kind="simulated" /></div>
          </div>
          <dl className="grid grid-cols-2 border-y border-dashed border-fog/25 sm:grid-cols-4">
            {[
              ["Diesel avoided", fmt.n(s?.diesel_l_avoided, 0), "L"],
              ["CO₂ avoided", fmt.n(s?.co2_kg_avoided), "kg"],
              ["Mill, cutter, batteries", fmt.n(s?.secondary_kwh), "kWh"],
              ["Farmers served", `${s?.farmers_served ?? "–"}`, `${s?.tenant_farmers_served ?? "–"} tenants`],
            ].map(([k, v, u]) => (
              <div key={k} className="py-3 pr-3">
                <dt className="text-[11.5px] text-mist">{k}</dt>
                <dd className="num mt-1 text-xl text-white">{v}<span className="ml-1 whitespace-nowrap text-[12px] text-mist">{u}</span></dd>
              </div>
            ))}
          </dl>

          <section aria-label="Integrity">
            <h2 className="text-[13px] font-medium text-fog">Is anything edited?</h2>
            <p className="mt-1 text-[13px] text-mist">Each receipt carries the SHA-256 of the one before it. Change one litre on one receipt and every hash after it breaks.</p>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <Btn tone="sun" onClick={runVerify} disabled={scan !== null}>{scan !== null ? "Checking…" : "Verify the whole chain"}</Btn>
              <Btn onClick={async () => setAudit(await getJSON<Audit>("/api/ledger/audit"))}>Run anomaly audit</Btn>
            </div>
            {verify && (
              <div role="status" className={`num mt-3 rounded-md border px-3 py-2 text-[13px] ${verify.ok ? "border-se/50 text-se" : "border-fault/60 text-fault"}`}>
                {verify.ok ? `Verified: ${verify.checked} receipts, chain intact` : `Broken at receipt #${verify.first_bad_seq}`}
                {verify.head && <div className="truncate text-[11px] opacity-80">head {verify.head}</div>}
              </div>
            )}
            {audit && (
              <div className="mt-3 text-[13px]">
                <div className="text-mist">{audit.n_findings} findings (physical rules + Isolation Forest)</div>
                <ul className="mt-1 max-h-40 overflow-y-auto" tabIndex={0}>
                  {audit.findings.map((f, i) => (
                    <li key={i} className="num text-[12px]"><span className={f.severity === "high" ? "text-fault" : "text-sun"}>{f.rule}</span> {f.receipt_id ?? ""} {f.detail}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="num mt-3 truncate text-[11px] text-mist">Merkle root {s?.merkle_root}</div>
          </section>

          <section aria-label="Claim pack for a funder">
            <h2 className="text-[13px] font-medium text-fog">Anudan Meter: turn receipts into a claim</h2>
            <form className="mt-2 flex flex-wrap items-end gap-3 text-[13px]" onSubmit={async (e) => { e.preventDefault(); setClaim(await getJSON<Claim>(`/api/ledger/claim?from_date=${from}&to_date=${to}`)); }}>
              <label className="flex flex-col gap-1 text-mist">From<input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="rounded border border-soil bg-night px-2 py-1 text-fog" /></label>
              <label className="flex flex-col gap-1 text-mist">To<input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="rounded border border-soil bg-night px-2 py-1 text-fog" /></label>
              <Btn type="submit" tone="sun">Build claim</Btn>
              <a className="rounded-md border border-soil px-2.5 py-1.5 text-[12px] hover:bg-night-3" href={`${API}/api/ledger/report.pdf`}>Funder PDF</a>
              <a className="rounded-md border border-soil px-2.5 py-1.5 text-[12px] hover:bg-night-3" href={`${API}/api/ledger/export.csv`}>CSV</a>
            </form>
            {claim && (
              <div className="paper mt-4 rounded-md p-4 text-ink">
                <div className="flex items-baseline justify-between"><span className="font-serif text-lg italic">Claim</span><span className="num text-[11px] opacity-70">{claim.funder} · {claim.period.join(" → ")}</span></div>
                <dl className="num mt-2 grid grid-cols-2 gap-y-1 text-[13px]">
                  <dt className="opacity-70">Water</dt><dd className="text-right">{fmt.n(claim.totals.m3)} m³</dd>
                  <dt className="opacity-70">Diesel avoided</dt><dd className="text-right">{fmt.n(claim.totals.diesel_l_avoided, 1)} L</dd>
                  <dt className="opacity-70">Subsidy equivalent</dt><dd className="text-right">{fmt.rs(claim.subsidy_equivalent_rs)}</dd>
                  <dt className="opacity-70">Receipts with hashes</dt><dd className="text-right">{fmt.n(claim.totals.receipts)}</dd>
                </dl>
                <p className="mt-2 border-t border-dashed border-ink/25 pt-2 text-[11.5px] opacity-75">{claim.status}. Diesel-subsidy equivalent at ₹75/L needs a rule change.</p>
              </div>
            )}
          </section>
        </div>

        {/* Right: the roll */}
        <section aria-label="Latest water receipts" className="relative min-w-0">
          <h2 className="mb-4 text-[13px] font-medium text-fog">The roll, newest first</h2>
          <ol className="relative mx-auto flex max-w-[440px] flex-col gap-4 pl-14">
            <span className="absolute bottom-6 left-[19px] top-6 w-px bg-[repeating-linear-gradient(to_bottom,var(--sun)_0_6px,transparent_6px_10px)] opacity-60" aria-hidden />
            {scan !== null && (
              <span className="pointer-events-none absolute -left-2 -right-2 z-10 h-[3px] rounded-full bg-sun shadow-[0_0_24px_6px_rgba(245,184,61,.45)] transition-[top] duration-150" style={{ top: `${(scan / Math.max(1, roll.length)) * 100}%` }} aria-hidden />
            )}
            {roll.map((r, i) => (
              <li key={r.seq} className="relative">
                <span className={`num absolute -left-14 top-5 flex h-10 w-10 items-center justify-center rounded-full border text-[9px] ${stampFor(i) === "verified" ? "border-sun/60 bg-night text-sun" : "border-soil bg-night text-mist"}`} title={`hash ${r.hash}`} aria-hidden>{r.hash.slice(0, 4)}</span>
                <Receipt r={r} fresh={i === 0} stamp={stampFor(i)} />
              </li>
            ))}
          </ol>
        </section>
      </div>

      <section aria-label="All receipts" className="mt-10">
        <h2 className="mb-2 text-[13px] font-medium text-fog">All receipts ({data?.total ?? "–"}) <span className="text-mist">· diesel counterfactual 1 L/h, 2.6444 kg CO₂/L</span> <SourceTag kind="published" /></h2>
        <div className="max-h-[420px] overflow-auto border-y border-soil" tabIndex={0} role="region" aria-label="All receipts table">
          <table className="num w-full min-w-[760px] text-[12px]">
            <thead className="sticky top-0 bg-night text-left text-mist">
              <tr>{["#", "Receipt", "Pump", "Kind", "Start", "Farmer", "m³", "kWh", "Diesel L", "₹", "Hash"].map((h) => <th key={h} className="py-1.5 font-normal">{h}</th>)}</tr>
            </thead>
            <tbody>
              {(data?.rows ?? []).map((r) => (
                <tr key={r.seq} className="border-t border-soil/60 hover:bg-night-2">
                  <td className="py-1 text-mist">{r.seq}</td>
                  <td>{r.receipt_id}</td>
                  <td className="text-mist">{r.pump_id}</td>
                  <td className={r.kind === "water" ? "text-water" : "text-sun"}>{r.kind}</td>
                  <td>{r.start.replace("T", " ")}</td>
                  <td>{r.farmer_ref ?? "–"}{r.tenant ? " ·T" : ""}</td>
                  <td>{r.m3.toFixed(1)}</td>
                  <td>{r.kwh.toFixed(2)}</td>
                  <td>{r.diesel_l_avoided.toFixed(2)}</td>
                  <td>{r.amount_rs.toFixed(0)}</td>
                  <td className="text-mist">{r.hash.slice(0, 10)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </Shell>
  );
}
