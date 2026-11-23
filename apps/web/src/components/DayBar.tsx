"use client";

import { area, curveMonotoneX, line } from "d3-shape";
import { type ReactNode, useCallback, useMemo, useRef, useState } from "react";
import { postJSON, useApi } from "@/lib/api";
import type { Snapshot } from "@/lib/types";

const DAY0 = 6 * 60;
const DAY1 = 18 * 60;
const toMin = (hhmm: string) => Number(hhmm.slice(0, 2)) * 60 + Number(hhmm.slice(3, 5));
const toHHMM = (m: number) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(Math.round(m % 60)).padStart(2, "0")}`;

/** Sky tint for a minute of the day: dawn rose -> noon white-gold -> dusk amber (the app's one light source). */
export function skyAt(min: number, cloud = false): string {
  const t = Math.min(1, Math.max(0, (min - DAY0) / (DAY1 - DAY0)));
  if (cloud && min >= 13 * 60 + 40 && min < 16 * 60 + 30) return "rgba(120,140,150,.22)";
  if (t < 0.18) return "rgba(232,140,120,.20)";
  if (t < 0.7) return "rgba(245,184,61,.16)";
  return "rgba(227,130,40,.24)";
}

/**
 * The day bar: the whole operating day of the real held-out date as one strip. Forecast band and actual sun
 * draw across it; the sun disc sits at "now" on the actual curve. Click (or arrow keys) to move the simulated
 * clock; going back replays the day from 06:00.
 */
export function DayBar({ title, actions }: { title: string; actions?: ReactNode }) {
  const { data, reload } = useApi<Snapshot>("/api/state", 2000);
  const [busy, setBusy] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [hover, setHover] = useState<number | null>(null);
  const track = useRef<HTMLDivElement>(null);

  const run = useCallback(
    async (fn: () => Promise<unknown>) => {
      setBusy(true);
      try {
        await fn();
      } finally {
        setBusy(false);
        reload();
      }
    },
    [reload],
  );
  const goTo = useCallback(
    (m: number) =>
      run(async () => {
        const target = Math.max(DAY0, Math.min(DAY1 - 10, Math.round(m / 10) * 10));
        const now = data ? toMin(data.clock) : DAY0;
        if (target < now) await postJSON("/api/demo/reset");
        await postJSON("/api/demo/run_to", { hhmm: toHHMM(target) });
      }),
    [data, run],
  );

  const W = 1000;
  const H = 40;
  const geo = useMemo(() => {
    const f = data?.forecast;
    if (!f) return null;
    const n = f.labels.length;
    const max = Math.max(0.1, ...f.q90, ...f.actual) * 1.08;
    const X = (i: number) => ((i + 0.5) / n) * W;
    const Y = (v: number) => H - (v / max) * (H - 4);
    const idx = f.labels.map((_, i) => i);
    const now = toMin(data.clock);
    const kNow = Math.max(0, Math.min(n - 1, Math.floor((now - DAY0) / 30)));
    const band = area<number>().x(X).y0((i) => Y(f.q10[i])).y1((i) => Y(f.q90[i])).curve(curveMonotoneX)(idx) ?? "";
    const actual = line<number>().x(X).y((i) => Y(f.actual[i])).curve(curveMonotoneX)(idx.slice(0, kNow + 1)) ?? "";
    const x = ((now - DAY0) / (DAY1 - DAY0)) * W;
    const frac = (now - DAY0) / 30 - 0.5;
    const i0 = Math.max(0, Math.min(n - 1, Math.floor(frac)));
    const i1 = Math.min(n - 1, i0 + 1);
    const v = f.actual[i0] + (f.actual[i1] - f.actual[i0]) * Math.max(0, Math.min(1, frac - i0));
    return { band, actual, x, y: Y(Math.max(0, v)), now, kw: v };
  }, [data]);

  const minAt = (clientX: number) => {
    const r = track.current?.getBoundingClientRect();
    if (!r) return DAY0;
    return DAY0 + ((clientX - r.left) / r.width) * (DAY1 - DAY0);
  };
  const now = geo?.now ?? DAY0;

  return (
    <header className="sticky top-0 z-10 border-b border-soil bg-night/92 backdrop-blur">
      <div className="pointer-events-none absolute inset-0 transition-[background] duration-700" style={{ background: `linear-gradient(90deg, transparent, ${skyAt(now, data?.cloud_applied)} ${((now - DAY0) / (DAY1 - DAY0)) * 100}%, transparent)` }} aria-hidden />
      <div className="relative flex flex-wrap items-center gap-x-4 gap-y-2 px-3 py-2 md:px-5">
        <h1 className="font-display text-base font-semibold tracking-tight md:text-lg">{title}</h1>
        <div className="num flex items-baseline gap-2 text-fog" aria-live="polite">
          <span className="text-2xl leading-none text-sun md:text-[28px]">{data?.clock ?? "--:--"}</span>
          <span className="hidden text-[11px] text-mist sm:inline">{data?.day} · Samastipur · real sun</span>
          {data?.cloud_applied && <span className="rounded bg-water/15 px-1.5 py-px text-[11px] text-water">nowcast</span>}
        </div>

        {/* The day strip */}
        <div className="order-last w-full md:order-none md:w-auto md:min-w-[260px] md:flex-1">
          <div
            ref={track}
            role="slider"
            tabIndex={0}
            aria-label="Simulated time of day"
            aria-valuemin={DAY0}
            aria-valuemax={DAY1}
            aria-valuenow={now}
            aria-valuetext={data?.clock ?? ""}
            aria-disabled={busy}
            className="relative h-7 cursor-pointer rounded-md outline-none md:h-10 focus-visible:ring-2 focus-visible:ring-sun"
            onClick={(e) => !busy && goTo(minAt(e.clientX))}
            onMouseMove={(e) => setHover(minAt(e.clientX))}
            onMouseLeave={() => setHover(null)}
            onKeyDown={(e) => {
              if (busy) return;
              if (e.key === "ArrowRight") goTo(now + 30);
              if (e.key === "ArrowLeft") goTo(now - 30);
              if (e.key === "Home") goTo(DAY0);
            }}
          >
            <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="absolute inset-0 h-full w-full overflow-visible" aria-hidden>
              {[8, 10, 12, 14, 16].map((h) => {
                const x = ((h * 60 - DAY0) / (DAY1 - DAY0)) * W;
                return <line key={h} x1={x} x2={x} y1={0} y2={H} stroke="var(--soil)" strokeWidth={1} vectorEffect="non-scaling-stroke" />;
              })}
              {geo && <path d={geo.band} fill="var(--sun)" opacity={0.28} />}
              {geo && <path d={geo.actual} fill="none" stroke="#fff" strokeWidth={1.6} vectorEffect="non-scaling-stroke" />}
              {geo && <line x1={geo.x} x2={geo.x} y1={0} y2={H} stroke="var(--sun)" strokeWidth={1} vectorEffect="non-scaling-stroke" />}
            </svg>
            {geo && (
              <span className="pointer-events-none absolute h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-sun shadow-[0_0_14px_4px_rgba(245,184,61,.55)] transition-[left,top] duration-500 ease-[cubic-bezier(.2,.7,.1,1)]"
                style={{ left: `${(geo.x / W) * 100}%`, top: `${(geo.y / H) * 100}%` }} aria-hidden />
            )}
            {hover !== null && (
              <span className="num pointer-events-none absolute -top-0.5 -translate-x-1/2 rounded bg-night px-1 text-[10px] text-fog" style={{ left: `${((hover - DAY0) / (DAY1 - DAY0)) * 100}%` }}>
                {toHHMM(Math.round(hover / 10) * 10)}
              </span>
            )}
          </div>
          <div className="num mt-0.5 hidden justify-between text-[10px] text-mist md:flex" aria-hidden>
            {["06", "08", "10", "12", "14", "16", "18"].map((h) => <span key={h}>{h}</span>)}
          </div>
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-1.5">
          {actions}
          <button
            disabled={busy}
            onClick={() => run(async () => { const next = !playing; setPlaying(next); await postJSON("/api/demo/autoplay", { on: next, speed: 60 }); })}
            className="hidden rounded-md border border-soil px-2.5 py-1 text-[12px] text-fog hover:bg-night-2 sm:inline-block"
          >
            {playing ? "Pause" : "Play ×60"}
          </button>
          <button disabled={busy} onClick={() => goTo(13 * 60 + 45)} className="rounded-md border border-water/60 px-2.5 py-1 text-[12px] text-water hover:bg-water/10">
            Jump to 13:45
          </button>
          <button disabled={busy} onClick={() => run(async () => { setPlaying(false); await postJSON("/api/demo/reset"); })} className="hidden rounded-md border border-soil px-2.5 py-1 text-[12px] text-mist hover:bg-night-2 sm:inline-block">
            Reset
          </button>
        </div>
      </div>
    </header>
  );
}
