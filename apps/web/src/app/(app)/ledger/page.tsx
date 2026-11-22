"use client";

import { useState } from "react";
import { Receipt } from "@/components/Receipt";
import { Shell } from "@/components/Shell";
import { Btn, ErrorNote, Panel, SourceTag, Stat } from "@/components/ui";
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
  const s = data?.summary;
  const water = (data?.rows ?? []).filter((r) => r.kind === "water");

  return (
    <Shell title="Rasid ledger">
      <ErrorNote error={error} />
      <div className="grid min-w-0 gap-4">
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
          <Panel><Stat value={fmt.n(s?.m3)} unit="m³" label="Solar water" tone="water" /></Panel>
          <Panel><Stat value={fmt.n(s?.diesel_l_avoided, 1)} unit="L" label="Diesel avoided" tone="leaf" /></Panel>
          <Panel><Stat value={fmt.n(s?.co2_kg_avoided)} unit="kg" label="CO₂ avoided" tone="leaf" /></Panel>
          <Panel><Stat value={fmt.n(s?.secondary_kwh)} unit="kWh" label="Mill, cutter, batteries" tone="sun" /></Panel>
          <Panel><Stat value={`${s?.farmers_served ?? "–"}`} label="Farmers served" sub={`${s?.tenant_farmers_served ?? "–"} of them tenants`} /></Panel>
          <Panel><Stat value={fmt.n(s?.receipts)} label="Receipts" sub={s ? `${s.first?.slice(0, 10)} to ${s.last?.slice(0, 10)}` : ""} /></Panel>
        </div>
        <p className="text-[12px] text-mist">
          History from the SinchaiSlot policy run on the synthetic village over real 2024 weather <SourceTag kind="simulated" />. Diesel
          counterfactual 1 L/h for a 5 HP diesel pump and 2.6444 kg CO₂ per litre <SourceTag kind="published" />.
        </p>
        <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
          <Panel
            title="Latest water receipts"
            right={
              <div className="flex gap-2">
                <a className="rounded-md border border-soil px-2.5 py-1 text-[12px] hover:bg-night-3" href={`${API}/api/ledger/export.csv`}>CSV</a>
                <a className="rounded-md border border-soil px-2.5 py-1 text-[12px] hover:bg-night-3" href={`${API}/api/ledger/report.pdf`}>Funder PDF</a>
              </div>
            }
          >
            <div className="grid gap-5 sm:grid-cols-2 2xl:grid-cols-3">
              {water.slice(0, 6).map((r, i) => <Receipt key={r.seq} r={r} fresh={i === 0} />)}
            </div>
          </Panel>
          <div className="flex min-w-0 flex-col gap-4">
            <Panel title="Integrity">
              <p className="text-[13px] text-mist">Each receipt carries the SHA-256 of the one before it. Editing any past receipt breaks every hash after it.</p>
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <Btn tone="sun" onClick={async () => setVerify(await getJSON<Verify>("/api/ledger/verify"))}>Verify the whole chain</Btn>
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
                  <ul className="mt-1 max-h-40 overflow-y-auto">
                    {audit.findings.map((f, i) => (
                      <li key={i} className="num text-[12px]">
                        <span className={f.severity === "high" ? "text-fault" : "text-sun"}>{f.rule}</span> {f.receipt_id ?? ""} {f.detail}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="num mt-3 truncate text-[11px] text-mist">Merkle root {s?.merkle_root}</div>
            </Panel>
            <Panel title="Anudan Meter: claim pack for a funder">
              <form
                className="flex flex-wrap items-end gap-3 text-[13px]"
                onSubmit={async (e) => {
                  e.preventDefault();
                  setClaim(await getJSON<Claim>(`/api/ledger/claim?from_date=${from}&to_date=${to}`));
                }}
              >
                <label className="flex flex-col gap-1">From<input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="rounded border border-soil bg-night px-2 py-1" /></label>
                <label className="flex flex-col gap-1">To<input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="rounded border border-soil bg-night px-2 py-1" /></label>
                <Btn type="submit" tone="sun">Build claim</Btn>
              </form>
              {claim && (
                <div className="mt-3 grid grid-cols-2 gap-3">
                  <Stat value={fmt.n(claim.totals.m3)} unit="m³" label="Water" tone="water" />
                  <Stat value={fmt.n(claim.totals.diesel_l_avoided, 1)} unit="L" label="Diesel avoided" tone="leaf" />
                  <Stat value={fmt.rs(claim.subsidy_equivalent_rs)} label="Diesel-subsidy equivalent" sub="at ₹75/L, needs a rule change" tone="sun" />
                  <Stat value={fmt.n(claim.totals.receipts)} label="Receipts with hashes" />
                  <p className="col-span-2 text-[12px] text-mist">{claim.status}</p>
                </div>
              )}
            </Panel>
          </div>
        </div>
        <Panel title={`All receipts (${data?.total ?? "–"})`}>
          <div className="max-h-[420px] overflow-auto" tabIndex={0} role="region" aria-label="All receipts table">
            <table className="num w-full min-w-[760px] text-[12px]">
              <thead className="sticky top-0 bg-night-2 text-left text-mist">
                <tr>{["#", "Receipt", "Kind", "Start", "Farmer", "m³", "kWh", "Diesel L", "₹", "Hash"].map((h) => <th key={h} className="py-1.5 font-normal">{h}</th>)}</tr>
              </thead>
              <tbody>
                {(data?.rows ?? []).map((r) => (
                  <tr key={r.seq} className="border-t border-soil">
                    <td className="py-1 text-mist">{r.seq}</td>
                    <td>{r.receipt_id}</td>
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
        </Panel>
      </div>
    </Shell>
  );
}
