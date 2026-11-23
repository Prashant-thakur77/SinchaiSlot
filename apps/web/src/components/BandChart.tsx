"use client";

import { scaleLinear } from "d3-scale";
import { area, curveMonotoneX, line } from "d3-shape";
import { useId } from "react";

type Props = {
  labels: string[];
  q10: number[];
  q50: number[];
  q90: number[];
  actual?: number[];
  actualUpTo?: number; // draw the actual line only up to this index (live "now")
  nowcast?: number[];
  nowIndex?: number;
  height?: number;
  yMax?: number;
  unit?: string;
  showAxis?: boolean;
  annotate?: { index: number; text: string }[];
  title?: string;
};

/** Forecast band: P10-P90 haze, P50 line, actual sun as a solid line, a "now" cursor. */
export function BandChart({
  labels,
  q10,
  q50,
  q90,
  actual,
  actualUpTo,
  nowcast,
  nowIndex,
  height = 220,
  yMax,
  unit = "kW",
  showAxis = true,
  annotate = [],
  title = "Solar power forecast with P10 to P90 band",
}: Props) {
  const id = useId().replace(/:/g, "");
  const W = 1000;
  const H = height;
  const pad = { l: showAxis ? 38 : 4, r: 8, t: 12, b: showAxis ? 26 : 4 };
  const n = labels.length;
  const max = yMax ?? Math.max(1, ...q90, ...(actual ?? [])) * 1.08;
  const x = scaleLinear().domain([0, n - 1]).range([pad.l, W - pad.r]);
  const y = scaleLinear().domain([0, max]).range([H - pad.b, pad.t]);
  const idx = labels.map((_, i) => i);
  const band = area<number>().x((i) => x(i)).y0((i) => y(q10[i])).y1((i) => y(q90[i])).curve(curveMonotoneX)(idx) ?? "";
  const mk = (arr: number[], upto = arr.length - 1) =>
    line<number>().x((i) => x(i)).y((i) => y(arr[i])).curve(curveMonotoneX)(idx.filter((i) => i <= upto)) ?? "";
  const ticks = y.ticks(4);
  const tickEvery = Math.max(1, Math.round(n / 8));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label={title}>
      <defs>
        <linearGradient id={`b${id}`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="var(--sun)" stopOpacity="0.38" />
          <stop offset="1" stopColor="var(--sun)" stopOpacity="0.08" />
        </linearGradient>
      </defs>
      {showAxis &&
        ticks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} stroke="var(--soil)" strokeWidth="1" />
            <text x={pad.l - 8} y={y(t) + 4} textAnchor="end" className="num" fontSize="11" fill="var(--mist)">
              {t}
            </text>
          </g>
        ))}
      {showAxis && (
        <text x={pad.l - 8} y={pad.t - 2} textAnchor="end" fontSize="10" fill="var(--mist)">
          {unit}
        </text>
      )}
      <path d={band} fill={`url(#b${id})`} />
      <path d={mk(q50)} fill="none" stroke="var(--sun-deep)" strokeWidth="2" strokeDasharray="6 5" />
      {nowcast && nowcast.length === n && (
        <path d={mk(nowcast)} fill="none" stroke="var(--water)" strokeWidth="1.5" strokeDasharray="2 4" opacity="0.8" />
      )}
      {actual && <path d={mk(actual, actualUpTo)} fill="none" stroke="var(--ink)" strokeWidth="2.6" strokeLinecap="round" />}
      {nowIndex !== undefined && nowIndex >= 0 && nowIndex < n && (
        <g>
          <line x1={x(nowIndex)} x2={x(nowIndex)} y1={pad.t} y2={H - pad.b} stroke="var(--water)" strokeWidth="1.5" />
          <circle cx={x(nowIndex)} cy={pad.t} r="4" fill="var(--water)" />
        </g>
      )}
      {annotate.map((a) => (
        <g key={a.index + a.text}>
          <line x1={x(a.index)} x2={x(a.index)} y1={pad.t + 14} y2={H - pad.b} stroke="var(--fog)" strokeDasharray="2 3" />
          <text x={x(a.index) + 6} y={pad.t + 12} fontSize="12" fill="var(--fog)">
            {a.text}
          </text>
        </g>
      ))}
      {showAxis &&
        labels.map((l, i) =>
          i % tickEvery === 0 ? (
            <text key={l + i} x={x(i)} y={H - 6} textAnchor="middle" className="num" fontSize="11" fill="var(--mist)">
              {l}
            </text>
          ) : null,
        )}
    </svg>
  );
}

export function BandLegend() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-mist">
      <span className="inline-flex items-center gap-1.5">
        <span className="h-2.5 w-5 rounded-sm bg-sun/30" /> P10 to P90 forecast
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="h-0 w-5 border-t-2 border-dashed border-sun-deep" /> P50 forecast
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="h-0 w-5 border-t-[3px] border-ink" /> Actual sun
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="h-3 w-px bg-water" /> Now
      </span>
    </div>
  );
}
