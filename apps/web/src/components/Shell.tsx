"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import { Motif } from "@/components/Art";
import { DayBar } from "@/components/DayBar";

type Item = { href: string; label: string; key: string; group: string; motif: string; what: string; icon: string };

export const NAV: Item[] = [
  { href: "/twin", label: "Village Twin", key: "1", group: "The day", motif: "sun", what: "See the fields, the pump and where the sun is going right now.", icon: "M3 12h4l3-8 4 16 3-8h4" },
  { href: "/planner", label: "Planner", key: "2", group: "The day", motif: "cloud", what: "Today's plan on the forecast. Drag a cloud across it to see what would move.", icon: "M4 6h16M4 12h10M4 18h6" },
  { href: "/cluster", label: "Pump cluster", key: "0", group: "The day", motif: "lotus", what: "Three pumps, one water table. Move a booking when one falls short.", icon: "M5 17a2 2 0 104 0 2 2 0 00-4 0M15 17a2 2 0 104 0 2 2 0 00-4 0M10 6a2 2 0 104 0 2 2 0 00-4 0M7 15l4-7M17 15l-4-7" },
  { href: "/phone", label: "Saathi phone", key: "3", group: "Farmers", motif: "parrot", what: "Give a missed call. Saathi calls back and books in the farmer's language.", icon: "M8 3h8v18H8zM11 18h2" },
  { href: "/mitra", label: "Saur Mitra app", key: "9", group: "Farmers", motif: "pump", what: "The operator's phone app.", icon: "M12 3a9 9 0 100 18 9 9 0 000-18zM12 7v5l3 2" },
  { href: "/hisaab", label: "Hisaab", key: "8", group: "Farmers", motif: "pot", what: "Ask the accounts a question in plain words.", icon: "M4 19h16M7 15V9M12 15V5M17 15v-4" },
  { href: "/judge", label: "Check it yourself", key: "j", group: "Proof", motif: "parrot", what: "Five questions, where to look, and what each answer does not show.", icon: "M4 12l5 5L20 6" },
  { href: "/rollout", label: "Will it pay here?", key: "r", group: "Proof", motif: "pot", what: "Pick a district, change the costs, see who earns what.", icon: "M12 21s7-6 7-11a7 7 0 10-14 0c0 5 7 11 7 11zM12 12.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5z" },
  { href: "/ledger", label: "Rasid ledger", key: "5", group: "Proof", motif: "fish", what: "Every litre has a receipt. Check the whole chain yourself.", icon: "M6 3h12v18l-3-2-3 2-3-2-3 2z" },
  { href: "/drive", label: "Altivar drive", key: "4", group: "Proof", motif: "wheel", what: "The drive that runs and meters the pump. Inject a fault and watch the response.", icon: "M4 5h16v14H4zM8 9h8M8 13h4" },
  { href: "/lab", label: "Prayogshala", key: "6", group: "Proof", motif: "tree", what: "How every number was tested, including what did not help.", icon: "M9 3v6L4 19h16L15 9V3" },
  { href: "/trace", label: "Agent trace", key: "7", group: "Proof", motif: "vine", what: "Every step the agents took, and what waited for a yes.", icon: "M5 5h4v4H5zM15 15h4v4h-4zM9 7h6v10" },
];
const GROUPS = ["The day", "Farmers", "Proof"];

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

  const here = NAV.find((n) => n.href === path) ?? (path.startsWith("/passport") ? { motif: "lotus", what: "One pump on one page, for a lender or a funder." } : undefined);
  const items = NAV.filter((n) => n.label.toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="flex min-h-dvh">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-sun focus:px-3 focus:py-1 focus:text-ink">
        Skip to content
      </a>
      <nav aria-label="Main" className="sticky top-0 z-20 hidden h-dvh w-[208px] shrink-0 flex-col border-r border-soil bg-night md:flex">
        <Link href="/" className="flex items-center gap-2 px-4 py-4">
          <Mark />
          <span className="font-display text-[24px]">SinchaiSlot</span>
        </Link>
        <div className="flex flex-1 flex-col gap-5 overflow-y-auto px-3 pt-2">
          {GROUPS.map((g) => (
            <div key={g}>
              <div className="px-3 pb-1 text-[13px] font-medium text-mist">{g}</div>
              <ul className="flex flex-col gap-0.5">
                {NAV.filter((n) => n.group === g).map((n) => {
                  const on = path === n.href;
                  return (
                    <li key={n.href}>
                      <Link
                        href={n.href}
                        aria-current={on ? "page" : undefined}
                        className={`flex items-center gap-2.5 rounded-full px-3 py-1.5 text-[14px] transition-colors ${on ? "bg-sun/35 font-medium text-ink" : "text-fog hover:bg-night-3"}`}
                      >
                        <Icon d={n.icon} />
                        <span className="flex-1">{n.label}</span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
        <button onClick={() => setPalette(true)} className="m-3 flex items-center justify-between rounded-full border border-soil px-3 py-1.5 text-[13px] text-mist hover:bg-night-3">
          Jump to… <kbd className="num">Ctrl K</kbd>
        </button>
      </nav>
      <div className="flex min-w-0 flex-1 flex-col">
        <DayBar />
        <nav aria-label="Main (mobile)" className="flex gap-1 overflow-x-auto border-b border-soil px-3 py-2 [mask-image:linear-gradient(90deg,#000_85%,transparent)] md:hidden">
          {NAV.map((n) => (
            <Link key={n.href} href={n.href} className={`shrink-0 rounded-full px-3 py-1.5 text-[13px] ${path === n.href ? "bg-sun text-ink" : "bg-night-3 text-fog"}`}>
              {n.label}
            </Link>
          ))}
        </nav>
        <main id="main" className="mx-auto w-full min-w-0 max-w-[1320px] flex-1 overflow-x-hidden px-4 pb-16 pt-5 md:px-8 md:pt-7">
          <div className="mb-6 flex flex-wrap items-center gap-x-4 gap-y-3">
            <Motif name={here?.motif ?? "sun"} size={68} />
            <div className="min-w-0 flex-1 basis-60">
              <h1 className="h-page">{title}</h1>
              {here && <p className="mt-0.5 max-w-[62ch] text-[15px] text-mist">{here.what}</p>}
            </div>
            {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
          </div>
          {children}
        </main>
      </div>
      {palette && (
        <div role="dialog" aria-modal="true" aria-label="Command palette" className="fixed inset-0 z-40 flex items-start justify-center bg-ink/40 p-4 pt-[15vh]" onClick={() => setPalette(false)}>
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

export function Mark({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <circle cx="16" cy="12" r="8" fill="var(--sun)" stroke="var(--ink)" strokeWidth="2" />
      <circle cx="13" cy="11" r="1.2" fill="var(--ink)" /><circle cx="19" cy="11" r="1.2" fill="var(--ink)" />
      <path d="M13 14.5q3 2.4 6 0" fill="none" stroke="var(--ink)" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M2 25q3.5-4 7 0t7 0 7 0 7 0" fill="none" stroke="var(--water-deep)" strokeWidth="2.6" strokeLinecap="round" />
    </svg>
  );
}
