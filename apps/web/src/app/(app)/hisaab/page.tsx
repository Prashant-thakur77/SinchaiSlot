"use client";

import { useEffect, useState } from "react";
import { Shell } from "@/components/Shell";
import { Btn } from "@/components/ui";
import { postJSON } from "@/lib/api";

type Answer = { answer: string; sql: string | null; columns?: string[]; rows?: (string | number | null)[][]; chart?: boolean };

const EXAMPLES = [
  "How much diesel did we avoid in February 2024?",
  "How much solar water in March 2024?",
  "Water to tenants vs landholders",
  "Revenue by service",
  "Mill and battery energy",
  "Daily water in February 2024",
  "पानी कितना दिया?",
];

export default function HisaabPage() {
  const [q, setQ] = useState(EXAMPLES[0]);
  const [a, setA] = useState<Answer | null>(null);
  const [busy, setBusy] = useState(false);
  const ask = async (question: string) => {
    setBusy(true);
    setQ(question);
    try {
      setA(await postJSON<Answer>("/api/agents/hisaab", { text: question }));
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    const t = setTimeout(() => ask(EXAMPLES[0]), 0);
    return () => clearTimeout(t);
     
  }, []);
  const numericCol = a?.columns && a.rows?.length ? a.columns.findLastIndex((_, i) => typeof a.rows![0][i] === "number") : -1;
  const max = numericCol >= 0 ? Math.max(...a!.rows!.map((r) => Number(r[numericCol]) || 0), 1e-9) : 1;
  return (
    <Shell title="Hisaab: ask the ledger">
      <div className="mx-auto flex max-w-4xl flex-col gap-4">
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); ask(q); }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} aria-label="Question about the ledger" className="deva min-w-0 flex-1 border-b-2 border-sun/60 bg-transparent px-1 py-2.5 font-display text-[clamp(1.1rem,2.2vw,1.6rem)] outline-none focus:border-sun" />
          <Btn type="submit" tone="sun" disabled={busy}>{busy ? "…" : "Ask"}</Btn>
        </form>
        <div className="flex flex-wrap gap-1.5">
          {EXAMPLES.map((e) => (
            <button key={e} onClick={() => ask(e)} className="deva rounded-full border border-soil px-3 py-1 text-[12px] text-fog hover:bg-night-2">{e}</button>
          ))}
        </div>
        {a && (
          <article className="paper perforated relative rounded-b-lg px-6 pb-6 pt-7 text-ink shadow-[0_24px_50px_-20px_rgba(0,0,0,.7)]" aria-live="polite">
            <div className="flex items-baseline justify-between gap-3 border-b border-ink/15 pb-2">
              <span className="font-serif text-xl italic">Hisaab</span>
              <span className="text-[11px] text-ink/60">read-only, row-limited SQL over verified receipts</span>
            </div>
            <p className="deva mt-3 font-serif text-[15px] italic text-ink/70">{q}</p>
            <p className="mt-2 bg-[repeating-linear-gradient(to_bottom,transparent_0_31px,rgba(19,32,26,.12)_31px_32px)] text-[22px] leading-[32px]">{a.answer}</p>
            {numericCol >= 0 && a.rows && a.rows.length > 1 && (
              <ul className="mt-4 flex flex-col gap-1.5">
                {a.rows.slice(0, 40).map((r, i) => (
                  <li key={i} className="grid grid-cols-[120px_minmax(0,1fr)_80px] items-center gap-3 text-[12.5px]">
                    <span className="num truncate text-ink/75">{String(r[0])}</span>
                    <span className="h-2.5 rounded-sm bg-[#1f6f9f]" style={{ width: `${(Number(r[numericCol]) / max) * 100}%` }} />
                    <span className="num text-right">{String(r[numericCol])}</span>
                  </li>
                ))}
              </ul>
            )}
            {a.sql && (
              <details className="mt-4">
                <summary className="cursor-pointer text-[12px] text-ink/65">SQL that ran</summary>
                <pre tabIndex={0} className="num mt-2 overflow-auto rounded bg-ink/5 p-3 text-[12px] text-ink/80">{a.sql}</pre>
              </details>
            )}
          </article>
        )}
      </div>
    </Shell>
  );
}
