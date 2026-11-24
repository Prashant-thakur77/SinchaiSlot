"use client";

import Link from "next/link";
import { type ReactNode, useState } from "react";
import { Shell } from "@/components/Shell";
import { ErrorNote, Panel, SourceTag } from "@/components/ui";
import { fmt, useApi } from "@/lib/api";
import { type District, type Inputs, unitEconomics } from "@/lib/economics";
import type { Proof } from "@/lib/types";

type Consts = Record<string, { value: number; source?: string }>;
const CHECKS = [
  ["machine", "Someone here owns a mill or chaff cutter and will use it"],
  ["near", "That machine is close enough to the pump for a cable"],
  ["phase", "It has a three-phase motor"],
] as const;

export default function RolloutPage() {
  const { data: p, error } = useApi<Proof>("/api/proof");
  const { data: sc } = useApi<{ districts: District[]; years: number[] }>("/api/scale");
  const { data: c } = useApi<Consts>("/api/constants");
  const [name, setName] = useState("Samastipur");
  const [mode, setMode] = useState<"new" | "retrofit">("retrofit");
  const [kit, setKit] = useState(60000);
  const [subsidy, setSubsidy] = useState(0.6);
  const [tariff, setTariff] = useState(3);
  const [demand, setDemand] = useState(0.7);
  const [millKg, setMillKg] = useState(120);
  const [packs, setPacks] = useState(6);
  const [selfRun, setSelfRun] = useState(true);
  const [checks, setChecks] = useState<Record<string, boolean>>({ machine: true, near: true, phase: true });
  const [crop, setCrop] = useState("wheat");

  const home = sc?.districts.find((d) => d.name === "Samastipur");
  const d = sc?.districts.find((x) => x.name === name);
  const loadsReady = CHECKS.every(([k]) => checks[k]);
  const ready = p && home && d && c;
  const k = c && { mitra: c.saur_mitra_revenue_share.value, platform: c.platform_revenue_share.value, tariff: c.sinchaislot_tariff_rs_per_m3.value, om: c.om_rs_per_year.value, co2: c.co2_kg_per_l_diesel.value };
  const input: Inputs = { mode, capex: c?.unit_capex_rs.value ?? 0, kit, subsidy, tariff, demand, millKg, packs, loadsReady, selfRun };
  const r = ready && k ? unitEconomics(p, home, d, input, k) : null;
  const diesel = p?.headline.diesel_rs_per_m3 ?? 4;
  const cr = d?.crops[crop];

  return (
    <Shell title="Will it pay here?">
      <ErrorNote error={error} />
      {ready && r && sc && (
        <div className="grid min-w-0 gap-5 xl:grid-cols-[400px_minmax(0,1fr)]">
          <Panel title="The place">
            <div className="flex flex-col gap-5">
              <label className="flex flex-col gap-1.5 text-[14px]">
                District
                <select value={name} onChange={(e) => setName(e.target.value)} className="min-h-11 rounded-lg border border-soil bg-paper px-3 text-[16px]">
                  {sc.districts.map((x) => <option key={x.name} value={x.name}>{x.name}, {x.state}</option>)}
                </select>
                <span className="text-[13px] text-mist">{fmt.n(d.pv_kwh_per_kwp)} kWh from each kWp a year, {fmt.n(d.rain_mm)} mm rain, {sc.years.join(" and ")} <SourceTag kind="real" /></span>
              </label>

              <fieldset>
                <legend className="text-[14px]">The pump</legend>
                <div className="mt-1.5 grid grid-cols-2 gap-2">
                  <Choice on={mode === "retrofit"} onClick={() => setMode("retrofit")}>Already in the village</Choice>
                  <Choice on={mode === "new"} onClick={() => setMode("new")}>Buy a new one</Choice>
                </div>
              </fieldset>
              {mode === "retrofit"
                ? <Slider label="Cost of drive, controller and cable" value={kit} set={setKit} min={20000} max={150000} step={5000} show={fmt.rs(kit)} note="No supplier quote yet. Move it to see how much it matters." />
                : <Slider label="Share of the ₹6 lakh paid by subsidy" value={subsidy} set={setSubsidy} min={0} max={0.9} step={0.05} show={fmt.pct(subsidy)} note="Chakhaji's solar entrepreneurs had 60%." />}

              <fieldset>
                <legend className="text-[14px]">Can spare sun be used here?</legend>
                <p className="mt-0.5 text-[13px] text-mist">
                  In a GIZ survey only {c.uspc_owners_running_other_machines.value} of {c.uspc_owners_surveyed.value} owners of a multi-machine controller ran anything but the pump. Among the reasons: no machine, pump too far from home, a single-phase motor.{" "}
                  <a className="underline" href={c.uspc_owners_surveyed.source} target="_blank" rel="noreferrer">Source</a>
                </p>
                <div className="mt-2 flex flex-col gap-1">
                  {CHECKS.map(([key, label]) => (
                    <label key={key} className="flex min-h-10 items-center gap-3 text-[14px]">
                      <input type="checkbox" checked={checks[key]} onChange={(e) => setChecks({ ...checks, [key]: e.target.checked })} className="h-5 w-5 shrink-0 accent-[var(--leaf-deep)]" />
                      {label}
                    </label>
                  ))}
                </div>
              </fieldset>

              <Slider label="Water price" value={tariff} set={setTariff} min={2} max={4} step={0.1} show={`₹${tariff.toFixed(2)} a m³`} note={`Diesel water costs about ₹${diesel.toFixed(2)} a m³.`} />
              <Slider label="Bookings, against the simulated village" value={demand} set={setDemand} min={0.3} max={1} step={0.05} show={fmt.pct(demand)} note="Starts below the simulation, because a new service fills slowly." />
              <Slider label="Flour brought to the mill" value={millKg} set={setMillKg} min={0} max={240} step={10} show={`${millKg} kg a day`} disabled={!loadsReady} />
              <Slider label="Battery packs charged" value={packs} set={setPacks} min={0} max={12} step={1} show={`${packs} a day`} />
              <fieldset>
                <legend className="text-[14px]">Who runs the pump day to day?</legend>
                <div className="mt-1.5 grid grid-cols-2 gap-2">
                  <Choice on={selfRun} onClick={() => setSelfRun(true)}>The owner or group</Choice>
                  <Choice on={!selfRun} onClick={() => setSelfRun(false)}>A paid Saur Mitra</Choice>
                </div>
              </fieldset>
            </div>
          </Panel>

          <div className="sticky bottom-0 z-10 -mx-4 -my-2 flex items-baseline justify-between border-y border-soil bg-paper px-4 py-3 xl:hidden" aria-hidden>
            <span className="text-[14px] text-mist">Pays for itself in</span><span className="num text-[22px] font-medium">{paybackText(r.payback)}</span>
          </div>
          <div className="flex min-w-0 flex-col gap-5">
            <Panel>
              <div aria-live="polite">
                <p className="text-[15px] text-mist">{mode === "retrofit" ? "The upgrade pays for itself in" : "The pump pays for itself in"}</p>
                <p className={`num mt-1 text-[44px] font-medium leading-none md:text-[64px] ${r.payback === null || r.payback > 7 ? "text-fault" : "text-leaf-ink"}`} data-testid="payback">
                  {paybackText(r.payback)}
                </p>
                <p className="mt-3 max-w-[62ch] text-[15px] text-fog">
                  {mode === "retrofit"
                    ? <>An owner who uses the pump only for their own fields is {fmt.rs(r.today)} a year better off with it. Here it becomes {fmt.rs(r.owner)}, for {fmt.rs(r.cost)} spent.{selfRun ? <> {fmt.rs(r.operator)} of that pays for their own work running it.</> : null}</>
                    : <>{fmt.rs(r.owner)} a year to the owner, for {fmt.rs(r.cost)} of their own money.</>}
                </p>
                {!loadsReady && <p className="mt-3 rounded-lg bg-sun/15 px-3 py-2 text-[14px] text-sun-ink">Without a machine that can be connected, the mill and cutter earn nothing. Plan on water and battery packs only, or choose another site.</p>}
                {!selfRun && mode === "retrofit" && <p className="mt-3 rounded-lg bg-sun/15 px-3 py-2 text-[14px] text-sun-ink">A paid operator takes {fmt.rs(r.operator)} of this. An owner already selling water by the hour earns about {fmt.rs(p.policies.B.owner_fpo_income_rs.p50)}, so they would lose by switching unless they or their group do the operator&apos;s work.</p>}
              </div>
            </Panel>

            <Panel title="Where the money comes from and goes" right={<SourceTag kind="model" />}>
              <Flow total={r.revenue} parts={[["Water", r.water, "var(--water)"], ["Flour mill", r.mill, "var(--sun)"], ["Chaff cutter", r.chaff, "var(--leaf)"], ["Battery packs", r.battery, "var(--rose)"]]} head={`${fmt.rs(r.revenue)} comes in`} />
              <dl className="mt-5 grid gap-x-6 gap-y-2 text-[14px] sm:grid-cols-2">
                <Row k="Operator (25% of sales)" v={fmt.rs(r.operator)} />
                <Row k="Platform (10% of sales)" v={fmt.rs(r.platform)} />
                <Row k="Upkeep" v={fmt.rs(r.om)} />
                <Row k="Diesel saved on owner's own fields" v={fmt.rs(r.ownWater)} />
                <Row k={selfRun ? "Owner keeps (with operator's share)" : "Owner keeps"} v={fmt.rs(r.owner)} strong />
              </dl>
            </Panel>

            <Panel title="What one farmer saves" right={<SourceTag kind="model" />}>
              <label className="flex flex-wrap items-center gap-3 text-[14px]">
                Crop
                <select value={crop} onChange={(e) => setCrop(e.target.value)} className="min-h-10 rounded-lg border border-soil bg-paper px-3 text-[15px]">
                  {Object.entries(d.crops).map(([id, x]) => <option key={id} value={id}>{x.name}</option>)}
                </select>
              </label>
              {cr && (
                <p className="mt-3 max-w-[62ch] text-[16px] leading-relaxed">
                  One acre in {d.name} needs about <b className="num">{fmt.n(cr.gross_m3_per_acre)} m³</b> in {cr.irrigations} irrigations. That is <b className="num">{fmt.rs(cr.gross_m3_per_acre * tariff)}</b> of solar water instead of {fmt.rs(cr.gross_m3_per_acre * diesel)} of diesel water:{" "}
                  <b className="num text-leaf-ink">{fmt.rs(cr.gross_m3_per_acre * (diesel - tariff))} saved</b>, if every irrigation is solar.
                </p>
              )}
              <p className="mt-2 text-[13px] text-mist">In the simulation solar met about {fmt.pct(p.policies.D.tenant_share_served_by_solar.p50)} of tenants&apos; need in a crowded command area, so a typical farmer saves on part of this.</p>
            </Panel>

            <div className="grid gap-5 md:grid-cols-2">
              <Panel title="Each pump, each year">
                <dl className="grid gap-2 text-[14px]">
                  <Row k="Solar water delivered" v={`${fmt.n(r.solarM3)} m³`} />
                  <Row k="Diesel not burned" v={`${fmt.n(r.dieselL)} L`} />
                  <Row k="CO₂ kept out" v={`${fmt.n(r.co2)} kg`} />
                </dl>
              </Panel>
              <Panel title="How this is worked out">
                <p className="text-[14px] text-fog">Starts from the simulated Samastipur pump in the <Link href="/lab" className="underline">Prayogshala</Link>, scaled by this district&apos;s real sun and your sliders. An estimate for choosing sites, not a second simulation. Sunnier places get no extra water, because the groundwater cap is kept. Check the block&apos;s groundwater category, well depth and local prices before any pilot.</p>
              </Panel>
            </div>
          </div>
        </div>
      )}
    </Shell>
  );
}

const paybackText = (y: number | null) => (y === null ? "never" : y < 1 ? `${Math.max(1, Math.round(y * 12))} months` : `${y.toFixed(1)} years`);

function Choice({ on, onClick, children }: { on: boolean; onClick: () => void; children: ReactNode }) {
  return <button type="button" aria-pressed={on} onClick={onClick} className={`min-h-11 rounded-full border px-3 text-[14px] ${on ? "border-ink bg-ink text-paper" : "border-soil text-fog hover:bg-night-3"}`}>{children}</button>;
}

function Slider({ label, value, set, min, max, step, show, note, disabled }: { label: string; value: number; set: (n: number) => void; min: number; max: number; step: number; show: string; note?: string; disabled?: boolean }) {
  return (
    <label className={`block text-[14px] ${disabled ? "opacity-70" : ""}`}>
      <span className="flex items-baseline justify-between gap-3"><span>{label}</span><span className="num font-medium">{show}</span></span>
      <input type="range" aria-label={label} aria-valuetext={show} min={min} max={max} step={step} value={value} disabled={disabled} onChange={(e) => set(Number(e.target.value))} className="mt-1.5 h-6 w-full accent-[var(--leaf-deep)]" />
      {note && <span className="block text-[13px] text-mist">{note}</span>}
    </label>
  );
}

function Row({ k, v, strong }: { k: string; v: string; strong?: boolean }) {
  return <div className={`flex items-baseline justify-between gap-4 border-b border-soil pb-1.5 ${strong ? "font-semibold" : ""}`}><dt className={strong ? "" : "text-fog"}>{k}</dt><dd className="num whitespace-nowrap">{v}</dd></div>;
}

function Flow({ total, parts, head }: { total: number; parts: [string, number, string][]; head: string }) {
  return (
    <div>
      <p className="num text-[20px] font-medium">{head}</p>
      <div className="mt-2 flex h-9 w-full gap-[2px] overflow-hidden rounded-full" role="img" aria-label={parts.map(([n, v]) => `${n} ${fmt.rs(v)}`).join(", ")}>
        {parts.filter((x) => x[1] > 0).map(([n, v, col]) => <div key={n} style={{ width: `${(v / total) * 100}%`, background: col }} className="transition-[width] duration-300 motion-reduce:transition-none" />)}
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[14px]">
        {parts.map(([n, v, col]) => <li key={n} className="flex items-center gap-2"><span className="h-3 w-3 rounded-full" style={{ background: col }} aria-hidden />{n} <span className="num text-mist">{fmt.rs(v)}</span></li>)}
      </ul>
    </div>
  );
}
