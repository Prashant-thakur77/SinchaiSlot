"use client";

/**
 * Energy flow, sun -> Altivar Solar drive -> pump (water) / flour mill / chaff cutter / battery packs.
 * Dash speed is proportional to the power on each path; idle paths are drawn faint and still.
 */
export function EnergyFlow({
  pvKw,
  pumpKw,
  flowM3h,
  activeLoad,
  loadKw,
  batteryKw,
  driveState,
  fault,
}: {
  pvKw: number;
  pumpKw: number;
  flowM3h: number;
  activeLoad: "mill" | "chaff" | null;
  loadKw: number;
  batteryKw: number;
  driveState: string;
  fault: string | null;
}) {
  const dur = (kw: number) => (kw > 0.05 ? `${Math.max(0.35, 2.4 - kw * 0.45)}s` : "0s");
  const path = (d: string, kw: number, color: string) => (
    <g>
      <path d={d} fill="none" stroke="var(--soil)" strokeWidth="7" strokeLinecap="round" />
      <path
        d={d}
        fill="none"
        stroke={kw > 0.05 ? color : "transparent"}
        strokeWidth="3"
        strokeLinecap="round"
        className={kw > 0.05 ? "flow-line" : ""}
        style={{ ["--flow-dur" as string]: dur(kw) }}
      />
    </g>
  );
  const node = (x: number, y: number, label: string, value: string, color: string, sub?: string) => (
    <g transform={`translate(${x},${y})`}>
      <rect x="-80" y="-34" width="160" height="68" rx="10" fill="var(--night-2)" stroke={color} strokeOpacity="0.7" />
      <text x="0" y="-10" textAnchor="middle" fontSize="15" fill="var(--mist)">
        {label}
      </text>
      <text x="0" y="18" textAnchor="middle" fontSize="21" fill="#fff" className="num">
        {value}
      </text>
      {sub && (
        <text x="96" y="6" textAnchor="start" fontSize="14" fill="var(--mist)" className="num">
          {sub}
        </text>
      )}
    </g>
  );
  return (
    <svg viewBox="0 0 800 340" className="block h-auto w-full" role="img"
      aria-label={`Energy flow: ${pvKw.toFixed(2)} kW solar, ${pumpKw.toFixed(2)} kW to the pump, ${loadKw.toFixed(2)} kW to ${activeLoad ?? "no load"}, ${batteryKw.toFixed(2)} kW to batteries`}>
      {/* sun */}
      <g transform="translate(90,165)">
        <circle r="44" fill="var(--sun)" opacity={0.18 + Math.min(pvKw / 5, 1) * 0.6} />
        <circle r="26" fill="var(--sun)" />
        <text y="74" textAnchor="middle" fontSize="15" fill="var(--mist)">Solar array 5 kWp</text>
        <text y="98" textAnchor="middle" fontSize="21" fill="#fff" className="num">{pvKw.toFixed(2)} kW</text>
      </g>
      {path("M 136 165 L 270 165", pvKw, "var(--sun)")}
      {/* drive */}
      <g transform="translate(330,165)">
        <rect x="-66" y="-52" width="132" height="104" rx="8" fill="#1d2b23" stroke={fault ? "var(--fault)" : "var(--se)"} strokeWidth="2" />
        <text y="-28" textAnchor="middle" fontSize="13" fill="var(--se)">Schneider</text>
        <text y="-8" textAnchor="middle" fontSize="15" fill="#fff">Altivar Solar</text>
        <text y="16" textAnchor="middle" fontSize="13" fill={fault ? "var(--fault)" : "var(--mist)"}>
          {fault ? `FAULT ${fault}` : driveState.replaceAll("_", " ")}
        </text>
        <text y="38" textAnchor="middle" fontSize="12" fill="var(--mist)">simulated drive</text>
      </g>
      {path("M 396 140 C 470 140 470 60 530 60", pumpKw, "var(--water)")}
      {path("M 396 165 C 470 165 470 165 530 165", loadKw, "var(--sun)")}
      {path("M 396 190 C 470 190 470 275 530 275", batteryKw, "var(--se)")}
      {node(610, 60, "Pump: water", `${flowM3h.toFixed(1)} m³/h`, "var(--water)", `${pumpKw.toFixed(1)} kW in`)}
      {node(610, 165, activeLoad === "chaff" ? "Chaff cutter" : "Flour mill", `${loadKw.toFixed(2)} kW`, "var(--sun)", activeLoad ? "on" : "idle")}
      {node(610, 275, "Battery packs", `${batteryKw.toFixed(2)} kW`, "var(--se)")}
    </svg>
  );
}
