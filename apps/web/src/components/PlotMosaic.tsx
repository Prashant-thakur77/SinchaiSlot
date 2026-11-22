"use client";

import { Delaunay } from "d3-delaunay";
import { useMemo } from "react";

/** Clip polygon `poly` to convex polygon `clip` (Sutherland-Hodgman). */
function clipPoly(poly: [number, number][], clip: [number, number][]): [number, number][] {
  let out = poly;
  for (let i = 0; i < clip.length; i++) {
    const [ax, ay] = clip[i];
    const [bx, by] = clip[(i + 1) % clip.length];
    const inside = ([x, y]: [number, number]) => (bx - ax) * (y - ay) - (by - ay) * (x - ax) >= 0;
    const inter = ([px, py]: [number, number], [qx, qy]: [number, number]): [number, number] => {
      const a1 = by - ay, b1 = ax - bx, c1 = a1 * ax + b1 * ay;
      const a2 = qy - py, b2 = px - qx, c2 = a2 * px + b2 * py;
      const d = a1 * b2 - a2 * b1 || 1e-9;
      return [(b2 * c1 - b1 * c2) / d, (a1 * c2 - a2 * c1) / d];
    };
    const input = out;
    out = [];
    for (let j = 0; j < input.length; j++) {
      const cur = input[j], prev = input[(j + input.length - 1) % input.length];
      if (inside(cur)) {
        if (!inside(prev)) out.push(inter(prev, cur));
        out.push(cur);
      } else if (inside(prev)) out.push(inter(prev, cur));
    }
    if (!out.length) break;
  }
  return out;
}

export type PlotFeature = {
  type: "Feature";
  geometry: { type: "Polygon"; coordinates: number[][][] };
  properties: {
    plot_id: string;
    farmer_id: string;
    farmer: string;
    tenant: boolean;
    owner: boolean;
    crop: string;
    stage: string;
    area_ha: number;
    need_m3: number;
    booking: string | null;
    slot: string | null;
    language: string;
  };
};

const CROP_FILL: Record<string, string> = {
  wheat: "#B8A15A",
  maize: "#7FA65A",
  potato: "#8C7A5B",
  paddy: "#5BBF6A",
  veg_summer: "#4F9E70",
  fallow: "#2A3A30",
};

/** The command area's plots (synthetic village, SIMULATED) as a schematic field mosaic, coloured by crop. */
export function PlotMosaic({
  features,
  pump,
  sellers = [],
  activeFarmer,
  selected,
  onSelect,
  cloud = false,
}: {
  features: PlotFeature[];
  pump?: { lon: number; lat: number };
  sellers?: { id: string; lon: number; lat: number; kind: string }[];
  activeFarmer?: string | null;
  selected?: string | null;
  onSelect?: (f: PlotFeature) => void;
  cloud?: boolean;
}) {
  const proj = useMemo(() => {
    const xs: number[] = [];
    const ys: number[] = [];
    for (const f of features)
      for (const [x, y] of f.geometry.coordinates[0]) {
        xs.push(x);
        ys.push(y);
      }
    for (const s of sellers) {
      xs.push(s.lon);
      ys.push(s.lat);
    }
    if (pump) {
      xs.push(pump.lon);
      ys.push(pump.lat);
    }
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    const k = Math.cos(((y0 + y1) / 2) * (Math.PI / 180));
    const w = (x1 - x0) * k || 1;
    const h = y1 - y0 || 1;
    const s = 900 / Math.max(w, h);
    return (lon: number, lat: number) => [50 + (lon - x0) * k * s, 50 + (y1 - lat) * s] as const;
  }, [features, sellers, pump]);

  // Schematic field mosaic: each plot becomes the Voronoi cell of its centre, clipped to the command
  // area, so the 20-acre command reads as contiguous fields with bunds between them.
  const cells = useMemo(() => {
    const centres = features.map((f) => {
      const ring = f.geometry.coordinates[0].slice(0, -1);
      const cx = ring.reduce((a, p) => a + p[0], 0) / ring.length;
      const cy = ring.reduce((a, p) => a + p[1], 0) / ring.length;
      return proj(cx, cy) as unknown as [number, number];
    });
    if (centres.length < 3) return [] as string[];
    const mx = centres.reduce((a, c) => a + c[0], 0) / centres.length;
    const my = centres.reduce((a, c) => a + c[1], 0) / centres.length;
    const r = Math.max(...centres.map((c) => Math.hypot(c[0] - mx, c[1] - my))) + 40;
    const boundary: [number, number][] = Array.from({ length: 40 }, (_, i) => {
      const a = (i / 40) * Math.PI * 2;
      const wob = 1 + 0.06 * Math.sin(a * 3) + 0.04 * Math.cos(a * 5);
      return [mx + r * wob * Math.cos(a), my + r * 0.9 * wob * Math.sin(a)];
    });
    const v = Delaunay.from(centres).voronoi([0, 0, 1000, 1000]);
    return centres.map((_, i) => {
      const poly = (v.cellPolygon(i) ?? []).slice(0, -1) as [number, number][];
      const c = clipPoly(poly, boundary);
      return c.map((p) => p.map((n) => n.toFixed(1)).join(",")).join(" ");
    });
  }, [features, proj]);

  return (
    <svg viewBox="0 0 1000 1000" className="block h-auto w-full" role="group" aria-label="Plots in the pump's command area">
      <defs>
        <radialGradient id="cloudShade" cx="50%" cy="50%" r="50%">
          <stop offset="0" stopColor="#0b1110" stopOpacity="0.55" />
          <stop offset="1" stopColor="#0b1110" stopOpacity="0" />
        </radialGradient>
        <pattern id="wet" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(30)">
          <rect width="8" height="8" fill="var(--water)" />
          <line x1="0" y1="0" x2="0" y2="8" stroke="#bfe6ff" strokeWidth="2" opacity="0.5" />
        </pattern>
      </defs>
      {features.map((f, i) => {
        const pts = cells[i] ?? "";
        const p = f.properties;
        const booked = p.booking && p.booking !== "cancelled";
        const active = activeFarmer === p.farmer_id;
        return (
          <polygon
            key={p.plot_id}
            points={pts}
            tabIndex={onSelect ? 0 : -1}
            role={onSelect ? "button" : undefined}
            aria-label={`${p.farmer}, ${p.crop}, ${p.area_ha.toFixed(2)} hectares${booked ? `, booked ${p.slot ?? ""}` : ""}`}
            onClick={() => onSelect?.(f)}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onSelect?.(f)}
            fill={active ? "url(#wet)" : booked ? "var(--water)" : CROP_FILL[p.crop] ?? "#2A3A30"}
            fillOpacity={booked || active ? 0.95 : 0.75}
            stroke={selected === p.plot_id ? "#fff" : "var(--night)"}
            strokeWidth={selected === p.plot_id ? 6 : 5}
            strokeLinejoin="round"
            className="cursor-pointer transition-[fill-opacity] duration-300 hover:fill-opacity-100 focus:outline-none"
          />
        );
      })}
      {features.map((f, i) => {
        if (!f.properties.tenant || !cells[i]) return null;
        const pts = cells[i].split(" ").map((p) => p.split(",").map(Number));
        const cx = pts.reduce((a, p) => a + p[0], 0) / pts.length;
        const cy = pts.reduce((a, p) => a + p[1], 0) / pts.length;
        return <circle key={`t${i}`} cx={cx} cy={cy} r="7" fill="var(--sun)" stroke="var(--night)" strokeWidth="2" className="pointer-events-none" />;
      })}
      {sellers.map((s) => {
        const [x, y] = proj(s.lon, s.lat);
        return (
          <g key={s.id} transform={`translate(${x},${y})`}>
            <rect x="-9" y="-9" width="18" height="18" rx="3" fill="var(--night-2)" stroke="var(--mist)" />
            <text y="4" textAnchor="middle" fontSize="11" fill="var(--mist)">{s.kind === "diesel" ? "D" : "E"}</text>
          </g>
        );
      })}
      {pump &&
        (() => {
          const [x, y] = proj(pump.lon, pump.lat);
          return (
            <g transform={`translate(${x},${y})`}>
              <circle r="26" fill="var(--sun)" opacity="0.25" />
              <circle r="14" fill="var(--sun)" stroke="var(--night)" strokeWidth="3" />
              <text y="44" textAnchor="middle" fontSize="20" fill="#fff">Pump P1</text>
            </g>
          );
        })()}
      {cloud && <ellipse cx="620" cy="420" rx="420" ry="300" fill="url(#cloudShade)" className="pointer-events-none" />}
    </svg>
  );
}

export function CropLegend() {
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-mist">
      {Object.entries(CROP_FILL).map(([k, c]) => (
        <span key={k} className="inline-flex items-center gap-1">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ background: c }} /> {k.replace("_", " ")}
        </span>
      ))}
      <span className="inline-flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-sm bg-water" /> booked today</span>
      <span className="inline-flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full bg-sun" /> tenant</span>
    </div>
  );
}
