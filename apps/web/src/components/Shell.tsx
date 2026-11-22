"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useCallback, useEffect, useState } from "react";
import { postJSON, useApi } from "@/lib/api";
import type { Snapshot } from "@/lib/types";

export const NAV = [
  { href: "/twin", label: "Village Twin", key: "1", icon: "M3 12h4l3-8 4 16 3-8h4" },
  { href: "/planner", label: "Planner", key: "2", icon: "M4 6h16M4 12h10M4 18h6" },
  { href: "/phone", label: "Saathi phone", key: "3", icon: "M8 3h8v18H8zM11 18h2" },
  { href: "/drive", label: "Altivar drive", key: "4", icon: "M4 5h16v14H4zM8 9h8M8 13h4" },
  { href: "/ledger", label: "Rasid ledger", key: "5", icon: "M6 3h12v18l-3-2-3 2-3-2-3 2z" },
  { href: "/lab", label: "Prayogshala", key: "6", icon: "M9 3v6L4 19h16L15 9V3" },
  { href: "/trace", label: "Agent trace", key: "7", icon: "M5 5h4v4H5zM15 15h4v4h-4zM9 7h6v10" },
  { href: "/hisaab", label: "Hisaab", key: "8", icon: "M4 19h16M7 15V9M12 15V5M17 15v-4" },
  { href: "/mitra", label: "Saur Mitra app", key: "9", icon: "M12 3a9 9 0 100 18 9 9 0 000-18zM12 7v5l3 2" },
];

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={d} />
    </svg>
  );
}

export function Shell({ title, children, actions }: { title: string; children: ReactNode; actions?: ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [palette, setPalette] = useState(false);
  const [q, setQ] = useState("");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = (e.target as HTMLElement)?.closest("input, textarea, [contenteditable]");
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((p) => !p);
        return;
      }
      if (e.key === "Escape") setPalette(false);
      if (typing || e.metaKey || e.ctrlKey || e.altKey) return;
      const n = NAV.find((x) => x.key === e.key);
      if (n) router.push(n.href);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router]);

  const items = NAV.filter((n) => n.label.toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="flex min-h-dvh">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-sun focus:px-3 focus:py-1 focus:text-ink">
        Skip to content
      </a>
      <nav aria-label="Main" className="sticky top-0 z-20 hidden h-dvh w-[200px] shrink-0 flex-col border-r border-soil bg-night md:flex">
        <Link href="/" className="flex items-center gap-2 px-4 py-4">
          <Mark />
          <span className="font-display text-[17px] font-semibold tracking-tight">SinchaiSlot</span>
        </Link>
        <ul className="flex flex-1 flex-col gap-0.5 px-2">
          {NAV.map((n) => {
            const on = path === n.href;
            return (
              <li key={n.href}>
                <Link
                  href={n.href}
                  aria-current={on ? "page" : undefined}
                  className={`flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] transition-colors ${on ? "bg-night-3 text-white" : "text-mist hover:bg-night-2 hover:text-fog"}`}
                >
                  <Icon d={n.icon} />
                  <span className="flex-1">{n.label}</span>
                  <kbd className="num text-[10px] text-mist/70">{n.key}</kbd>
                </Link>
              </li>
            );
          })}
        </ul>
        <button onClick={() => setPalette(true)} className="m-3 flex items-center justify-between rounded-md border border-soil px-2.5 py-1.5 text-[12px] text-mist hover:bg-night-2">
          Jump to… <kbd className="num">Ctrl K</kbd>
        </button>
      </nav>
      <div className="flex min-w-0 flex-1 flex-col">
        <DemoBar title={title} actions={actions} />
        <nav aria-label="Main (mobile)" className="flex gap-1 overflow-x-auto border-b border-soil px-3 py-2 md:hidden">
          {NAV.map((n) => (
            <Link key={n.href} href={n.href} className={`shrink-0 rounded-full px-3 py-1 text-[12px] ${path === n.href ? "bg-sun text-ink" : "bg-night-2 text-fog"}`}>
              {n.label}
            </Link>
          ))}
        </nav>
        <main id="main" className="min-w-0 flex-1 overflow-x-hidden p-3 md:p-5">
          {children}
        </main>
      </div>
      {palette && (
        <div role="dialog" aria-modal="true" aria-label="Command palette" className="fixed inset-0 z-40 flex items-start justify-center bg-black/50 p-4 pt-[15vh]" onClick={() => setPalette(false)}>
          <div className="w-full max-w-md overflow-hidden rounded-lg border border-soil bg-night-2" onClick={(e) => e.stopPropagation()}>
            <input
              autoFocus
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && items[0]) {
                  router.push(items[0].href);
                  setPalette(false);
                }
              }}
              placeholder="Go to a screen…"
              aria-label="Search screens"
              className="w-full border-b border-soil bg-transparent px-4 py-3 text-sm outline-none"
            />
            <ul className="max-h-80 overflow-y-auto p-1">
              {items.map((n) => (
                <li key={n.href}>
                  <button
                    onClick={() => {
                      router.push(n.href);
                      setPalette(false);
                    }}
                    className="flex w-full items-center gap-2.5 rounded px-3 py-2 text-left text-sm text-fog hover:bg-night-3"
                  >
                    <Icon d={n.icon} /> {n.label}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}

export function Mark({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <circle cx="16" cy="12" r="7" fill="var(--sun)" />
      <path d="M3 24c4-3 8-3 13 0s9 3 13 0" fill="none" stroke="var(--water)" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

/** Top bar: the demo clock and controls (the day is a real held-out day, replayed). */
function DemoBar({ title, actions }: { title: string; actions?: ReactNode }) {
  const { data, reload } = useApi<Snapshot>("/api/state", 2000);
  const [busy, setBusy] = useState(false);
  const [playing, setPlaying] = useState(false);
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
  return (
    <header className="sticky top-0 z-10 flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-soil bg-night/90 px-3 py-2 backdrop-blur md:px-5 md:py-2.5">
      <h1 className="font-display text-base font-semibold tracking-tight md:text-lg">{title}</h1>
      <div className="flex items-center gap-2 text-[12px] text-mist">
        <span className="num rounded bg-night-2 px-2 py-0.5 text-fog" aria-live="polite">
          {data ? `${data.day} · ${data.clock}` : "…"}
        </span>
        <span className="hidden lg:inline">Samastipur · held-out day, real sun</span>
        {data?.cloud_applied && <span className="rounded bg-water/15 px-2 py-0.5 text-water">nowcast active</span>}
      </div>
      <div className="ml-auto flex flex-wrap items-center gap-1.5">
        {actions}
        <button
          disabled={busy}
          onClick={() =>
            run(async () => {
              const next = !playing;
              setPlaying(next);
              await postJSON("/api/demo/autoplay", { on: next, speed: 60 });
            })
          }
          className="rounded-md border border-soil px-2.5 py-1 text-[12px] text-fog hover:bg-night-2"
        >
          {playing ? "Pause" : "Play day ×60"}
        </button>
        <button disabled={busy} onClick={() => run(() => postJSON("/api/demo/advance", { minutes: 30 }))} className="hidden rounded-md border sm:inline-block border-soil px-2.5 py-1 text-[12px] text-fog hover:bg-night-2">
          +30 min
        </button>
        <button disabled={busy} onClick={() => run(() => postJSON("/api/demo/run_to", { hhmm: "13:45" }))} className="rounded-md border border-water/60 px-2.5 py-1 text-[12px] text-water hover:bg-water/10">
          Jump to 13:45
        </button>
        <button
          disabled={busy}
          onClick={() =>
            run(async () => {
              setPlaying(false);
              await postJSON("/api/demo/reset");
            })
          }
          className="hidden rounded-md border border-soil px-2.5 py-1 text-[12px] text-mist hover:bg-night-2 sm:inline-block"
        >
          Reset 06:00
        </button>
      </div>
    </header>
  );
}
