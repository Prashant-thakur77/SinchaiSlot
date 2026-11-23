"use client";

import { scaleLinear } from "d3-scale";
import { line } from "d3-shape";
import { useState } from "react";
import { Shell } from "@/components/Shell";
import { Btn, ErrorNote, Panel, SourceTag } from "@/components/ui";
import { postJSON, useApi } from "@/lib/api";
import type { Telemetry } from "@/lib/types";

type Drive = Telemetry & { pv_kw_available: number; extras: { low_light: boolean; flow_m3h_true: number; note: string }; unverified_registers: string[] };
type Calib = { curve: { kw: number; m3h: number }[]; calibration_points: { kw: number; estimate_m3h: number; meter_m3h: number }[]; k: number; cutoff_kw: number; label: string };
type Fault = { mnemonic: string; name: string; lft: number | null; description: string; verified: boolean };
type Diagnosis = { fault: string | null; name?: string; step?: number; of?: number; instruction_en: string; instruction_hi: string | null; source?: string; done: boolean; next_tool?: string | null; candidates?: { fault: string; name: string; score: number }[] };

const ROWS: { key: keyof Telemetry; label: string; reg: string; addr: number; unit: string; digits?: number }[] = [
  { key: "state", label: "State (ETA)", reg: "ETA", addr: 3201, unit: "" },
  { key: "freq_hz", label: "Output frequency", reg: "RFR", addr: 3202, unit: "Hz", digits: 1 },
  { key: "speed_rpm", label: "Motor speed", reg: "RFRD", addr: 8604, unit: "rpm" },
  { key: "current_a", label: "Motor current", reg: "LCR", addr: 3204, unit: "A", digits: 1 },
  { key: "power_pct", label: "Motor power", reg: "OPR", addr: 3211, unit: "% nom." },
  { key: "motor_v", label: "Motor voltage", reg: "UOP", addr: 3208, unit: "V" },
  { key: "thermal_pct", label: "Drive thermal state", reg: "THD", addr: 3209, unit: "%" },
  { key: "energy_kwh", label: "Energy", reg: "APH + UNT", addr: 3230, unit: "kWh" },
  { key: "fault_lft", label: "Last fault", reg: "LFT", addr: 7121, unit: "" },
];

export default function DrivePage() {
  const { data: d, error, reload } = useApi<Drive>("/api/drive", 1500);
  const { data: cal } = useApi<Calib>("/api/drive/calibration");
  const { data: faults } = useApi<Fault[]>("/api/drive/faults");
  const [fault, setFault] = useState("OHF");
  const [diag, setDiag] = useState<Diagnosis | null>(null);
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
    } finally {
      setBusy(false);
      reload();
    }
  };
  const ask = async (k: number, obs = "") => {
    const r = await postJSON<{ diagnosis: Diagnosis }>("/api/agents/copilot", { text: `${d?.fault ?? ""} fault`, session_id: "drive-page", step: k, observation: obs });
    setDiag(r.diagnosis);
    setStep(k);
  };
  const running = d?.state === "operation_enabled";

  return (
    <Shell title="Schneider Altivar Solar">
      <ErrorNote error={error} />
      <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          {/* Faceplate */}
          <div className="device rounded-xl border border-ink bg-[#344a3f] p-5 shadow-xl">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-[12px] font-semibold tracking-wide text-se-ink">Schneider Electric</div>
                <div className="text-xl font-semibold">Altivar Solar ATV320</div>
              </div>
              <div className="text-right text-[12px] text-mist">
                Modbus ID 1 · 19200 8E1
                <br />
                <span className="text-water-ink">simulated drive</span> <SourceTag kind="simulated" />
              </div>
            </div>
            <div className="mt-4 grid grid-cols-[1fr_auto] gap-4">
              <div className="rounded-md border border-black/50 bg-[#0a1210] p-4 shadow-inner" aria-live="polite">
                <div className="num text-[12px] text-se-ink/80">{d?.fault ? "FLT" : running ? (d?.extras.low_light ? "LOW LIGHT" : "RUN") : "RDY"}</div>
                <div className="num text-5xl tracking-tight text-se-ink" style={{ textShadow: "0 0 12px rgba(61,205,88,.45)" }}>
                  {d?.fault ? d.fault : `${(d?.freq_hz ?? 0).toFixed(1)}`}
                  {!d?.fault && <span className="ml-1 text-xl">Hz</span>}
                </div>
                <div className="num mt-2 grid grid-cols-3 gap-2 text-[13px] text-se-ink/90">
                  <span>{(d?.power_kw ?? 0).toFixed(2)} kW</span>
                  <span>{(d?.current_a ?? 0).toFixed(1)} A</span>
                  <span>{(d?.energy_kwh ?? 0).toFixed(0)} kWh</span>
                </div>
              </div>
              <div className="flex flex-col justify-center gap-2 text-[12px]">
                {[
                  { l: "RDY", on: !!d && !d.fault, c: "bg-se" },
                  { l: "RUN", on: running && !d?.extras.low_light, c: "bg-se" },
                  { l: "FLT", on: !!d?.fault, c: "bg-fault" },
                ].map((x) => (
                  <div key={x.l} className="flex items-center gap-2">
                    <span className={`h-3 w-3 rounded-full ${x.on ? x.c : "bg-[#2a332f]"}`} style={x.on ? { boxShadow: "0 0 8px currentColor" } : {}} />
                    <span className="num text-mist">{x.l}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <label className="text-[12px] text-mist">
                Inject fault{" "}
                <select value={fault} onChange={(e) => setFault(e.target.value)} className="ml-1 rounded border border-soil bg-night px-2 py-1 text-fog">
                  {(faults ?? []).filter((f) => f.lft !== null).map((f) => (
                    <option key={f.mnemonic} value={f.mnemonic}>{f.mnemonic}: {f.name}</option>
                  ))}
                </select>
              </label>
              <Btn tone="fault" disabled={busy} onClick={() => act(async () => { await postJSON("/api/drive/fault", { fault }); setDiag(null); })}>Inject</Btn>
              <Btn disabled={busy} onClick={() => act(() => postJSON("/api/drive/dry_run", { on: true }))}>Well runs dry</Btn>
              <Btn disabled={busy} onClick={() => act(() => postJSON("/api/drive/dry_run", { on: false }))}>Water back</Btn>
            </div>
            <p className="mt-2 text-[12px] text-mist">{d?.extras.note}</p>
          </div>

          <Panel title="Telemetry, register by register" right={<span className="text-[12px] text-mist">addresses from the ATV320 Modbus manual NVE41308</span>}>
            <table className="num w-full text-[13px]">
              <thead>
                <tr className="text-left text-[12px] text-mist">
                  <th className="pb-2 font-normal">Value</th>
                  <th className="pb-2 font-normal">Register</th>
                  <th className="pb-2 text-right font-normal">Reading</th>
                </tr>
              </thead>
              <tbody>
                {ROWS.map((r) => {
                  const v = d?.[r.key];
                  return (
                    <tr key={r.reg} className="border-t border-soil">
                      <td className="py-1.5 font-sans">{r.label}</td>
                      <td className="py-1.5 text-mist">{r.reg} <span className="text-[12px]">@{r.addr}</span></td>
                      <td className="py-1.5 text-right">
                        {typeof v === "number" ? v.toFixed(r.digits ?? 0) : String(v ?? "–").replaceAll("_", " ")} <span className="text-mist">{r.unit}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="mt-3 text-[12px] text-mist">
              No published Modbus address exists for PV voltage, PV power, MPPT state or the drive&apos;s own flow estimate; they are
              marked UNVERIFIED and never read over Modbus: {d?.unverified_registers.slice(-6).join(", ")}.
            </p>
          </Panel>
        </div>

        <div className="flex min-w-0 flex-col gap-4">
          <Panel title="The drive is the meter" right={<SourceTag kind="model" />}>
            {cal && <CalibChart cal={cal} />}
            <p className="mt-2 text-[12px] text-mist">
              Water is estimated from the drive&apos;s frequency (pump curve, affinity laws) and cross-checked with its power. A flow meter
              is needed only to calibrate: fitted factor k = <span className="num text-fog">{cal?.k.toFixed(3)}</span>. Below{" "}
              <span className="num">{cal?.cutoff_kw.toFixed(2)} kW</span> the pump lifts no water, so the planner sends that sun to the mill
              or batteries. {cal?.label}
            </p>
          </Panel>

          <Panel title="Saur Mitra Copilot: guided fix" right={d?.fault ? <span className="text-[12px] text-fault">Fault {d.fault}: {d.fault_name}</span> : <span className="text-[12px] text-mist">no fault</span>}>
            {!d?.fault && !diag && <p className="text-sm text-mist">Inject a fault on the faceplate. The Copilot reads the fault code from the drive (register LFT) and walks the Saur Mitra through the fix, step by step.</p>}
            {d?.fault && !diag && <Btn tone="sun" onClick={() => ask(0)}>Start the guided fix</Btn>}
            {diag && (
              <div className="flex flex-col gap-3">
                <div className="num text-[12px] text-mist">
                  Step {(diag.step ?? 0) + 1} of {diag.of ?? 1} · {diag.source}
                </div>
                {diag.instruction_hi && <p className="deva text-lg" lang="hi">{diag.instruction_hi}</p>}
                <p className={diag.instruction_hi ? "text-[13px] text-mist" : "text-[15px]"}>{diag.instruction_en}</p>
                <div className="flex flex-wrap gap-2">
                  {!diag.done && <Btn tone="sun" onClick={() => ask(step + 1)}>Done, next step</Btn>}
                  {diag.done && (
                    <Btn
                      tone="sun"
                      onClick={() =>
                        act(async () => {
                          await postJSON("/api/agents/copilot", { text: "haan", session_id: "drive-page" });
                          setDiag(null);
                        })
                      }
                    >
                      Reset the drive (confirm)
                    </Btn>
                  )}
                  <Btn onClick={() => setDiag(null)}>Close</Btn>
                </div>
              </div>
            )}
          </Panel>
        </div>
      </div>
    </Shell>
  );
}

function CalibChart({ cal }: { cal: Calib }) {
  const W = 600, H = 240, p = { l: 44, r: 12, t: 12, b: 34 };
  const x = scaleLinear().domain([0, 3.8]).range([p.l, W - p.r]);
  const y = scaleLinear().domain([0, 34]).range([H - p.b, p.t]);
  const path = line<{ kw: number; m3h: number }>().x((d) => x(d.kw)).y((d) => y(d.m3h))(cal.curve) ?? "";
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Pump flow against drive power, with flow-meter calibration points">
      {y.ticks(4).map((t) => (
        <g key={t}>
          <line x1={p.l} x2={W - p.r} y1={y(t)} y2={y(t)} stroke="var(--soil)" />
          <text x={p.l - 6} y={y(t) + 4} textAnchor="end" fontSize="11" fill="var(--mist)" className="num">{t}</text>
        </g>
      ))}
      {x.ticks(4).map((t) => (
        <text key={t} x={x(t)} y={H - 14} textAnchor="middle" fontSize="11" fill="var(--mist)" className="num">{t} kW</text>
      ))}
      <text x={p.l} y={p.t + 4} fontSize="11" fill="var(--mist)">m³/h</text>
      <rect x={p.l} y={p.t} width={x(cal.cutoff_kw) - p.l} height={H - p.b - p.t} fill="var(--sun)" opacity="0.08" />
      <path d={path} fill="none" stroke="var(--water)" strokeWidth="2.5" />
      {cal.calibration_points.map((c, i) => (
        <circle key={i} cx={x(c.kw)} cy={y(c.meter_m3h)} r="4" fill="var(--se)" />
      ))}
    </svg>
  );
}
