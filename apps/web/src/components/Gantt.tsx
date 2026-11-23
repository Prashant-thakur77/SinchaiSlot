"use client";

import { LayoutGroup, motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";
import type { Slot } from "@/lib/types";

type Seg = { start: number; len: number; m3: number };

function segments(slots: Slot[], match: (s: Slot) => boolean): Seg[] {
  const out: Seg[] = [];
  slots.forEach((s, k) => {
    if (!match(s)) return;
    const last = out[out.length - 1];
    if (last && last.start + last.len === k) {
      last.len += 1;
      last.m3 += s.water_m3.P50;
    } else out.push({ start: k, len: 1, m3: s.water_m3.P50 });
  });
  return out;
}

/**
 * Plan timeline: one row per booking plus rows for the mill, chaff cutter and battery packs.
 * Contiguous runs are layout-animated, so when the plan re-flows each block slides to its new time.
 */
type Tr = { duration: number } | { type: "tween"; duration: number; ease: readonly [number, number, number, number] };

function Track({ label, sub, children, n, nowIndex, h }: { label: string; sub?: string; children: ReactNode; n: number; nowIndex?: number; h: string }) {
  return (
    <div className="flex items-center gap-3">
      <div className="w-[128px] shrink-0 truncate text-[12px] text-fog">
        {label}
        {sub && <span className="ml-1.5 text-[10px] text-mist">{sub}</span>}
      </div>
      <div className={`relative ${h} flex-1 rounded-[3px] bg-night-3/70`}>
        {Array.from({ length: n / 2 }, (_, i) => (
          <div key={i} className="absolute inset-y-0 w-px bg-night" style={{ left: `${((i * 2) / n) * 100}%` }} aria-hidden />
        ))}
        {children}
        {nowIndex !== undefined && nowIndex >= 0 && nowIndex < n && (
          <div className="absolute -inset-y-1 w-[2px] bg-water" style={{ left: `${((nowIndex + 0.5) / n) * 100}%` }} aria-hidden />
        )}
      </div>
    </div>
  );
}

function Block({ id, seg, cls, title, n, tr }: { id: string; seg: Seg; cls: string; title: string; n: number; tr: Tr }) {
  return (
    <motion.div
      layout
      layoutId={id}
      transition={tr}
      title={title}
      className={`absolute inset-y-[3px] rounded-[3px] ${cls}`}
      style={{ left: `${(seg.start / n) * 100}%`, width: `calc(${(seg.len / n) * 100}% - 2px)` }}
    />
  );
}

export function Gantt({
  slots,
  nowIndex,
  highlight,
  compact = false,
}: {
  slots: Slot[];
  nowIndex?: number;
  highlight?: Set<string>;
  compact?: boolean;
}) {
  const reduce = useReducedMotion();
  const n = slots.length || 24;
  const tr: Tr = reduce ? { duration: 0 } : { type: "tween" as const, duration: 0.52, ease: [0.2, 0.7, 0.1, 1] as const };
  const rows = new Map<string, { label: string; tenant: boolean | null }>();
  for (const s of slots) if (s.action === "req" && s.booking_id) rows.set(s.booking_id, { label: s.farmer ?? s.booking_id, tenant: s.tenant });
  const keys = [...rows.keys()].sort();
  const bmax = Math.max(0.01, ...slots.map((s) => s.battery_kwh));
  const h = compact ? "h-5" : "h-7";

  return (
    <div className="min-w-0 overflow-x-auto" role="figure" tabIndex={0} aria-label="Today's plan by 30-minute slot">
      <div className="flex min-w-[640px] flex-col gap-1.5">
        <div className="flex items-center gap-3">
          <div className="w-[128px] shrink-0" />
          <div className="relative h-4 flex-1">
            {slots.map((s, k) =>
              k % 4 === 0 ? (
                <span key={s.start} className="num absolute -translate-x-1/2 text-[10px] text-mist" style={{ left: `${(k / n) * 100}%` }}>
                  {s.start}
                </span>
              ) : null,
            )}
          </div>
        </div>
        <LayoutGroup>
          {keys.map((key) => {
            const r = rows.get(key)!;
            return (
              <Track n={n} nowIndex={nowIndex} h={h} key={key} label={r.label} sub={r.tenant ? "tenant" : undefined}>
                {segments(slots, (s) => s.action === "req" && s.booking_id === key).map((seg, i) => (
                  <Block n={n} tr={tr}
                    key={`${key}-${i}`}
                    id={`${key}-${i}`}
                    seg={seg}
                    cls={highlight?.has(key) ? "bg-water ring-2 ring-white" : "bg-water/85"}
                    title={`${r.label} ${slots[seg.start].start}, ${seg.len * 30} min, ${seg.m3.toFixed(1)} m³ (P50)`}
                  />
                ))}
              </Track>
            );
          })}
          {keys.length === 0 && (
            <Track n={n} nowIndex={nowIndex} h={h} label="Water">
              <span className="absolute inset-0 flex items-center pl-2 text-[11px] text-mist">No bookings today</span>
            </Track>
          )}
          <Track n={n} nowIndex={nowIndex} h={h} label="Flour mill">
            {segments(slots, (s) => s.action === "mill").map((seg, i) => (
              <Block n={n} tr={tr} key={`mill-${i}`} id={`mill-${i}`} seg={seg} cls="bg-sun" title={`Mill from ${slots[seg.start].start}`} />
            ))}
          </Track>
          <Track n={n} nowIndex={nowIndex} h={h} label="Chaff cutter">
            {segments(slots, (s) => s.action === "chaff").map((seg, i) => (
              <Block n={n} tr={tr} key={`chaff-${i}`} id={`chaff-${i}`} seg={seg} cls="bg-[#c98b4a]" title={`Chaff cutter from ${slots[seg.start].start}`} />
            ))}
          </Track>
          <Track n={n} nowIndex={nowIndex} h={h} label="Battery packs">
            {slots.map((s, k) =>
              s.battery_kwh > 0.01 ? (
                <div
                  key={`b${k}`}
                  className="absolute bottom-[3px] rounded-[2px] bg-mist/70"
                  title={`${s.battery_kwh.toFixed(2)} kWh at ${s.start}`}
                  style={{ left: `${(k / n) * 100}%`, width: `calc(${100 / n}% - 2px)`, height: `${Math.max(18, (s.battery_kwh / bmax) * 80)}%` }}
                />
              ) : null,
            )}
          </Track>
        </LayoutGroup>
      </div>
    </div>
  );
}
