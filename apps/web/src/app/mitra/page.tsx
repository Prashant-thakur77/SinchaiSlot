"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { OPERATOR_TOKEN, postJSON, useApi } from "@/lib/api";

type Booking = { id: string; farmer: string; tenant: boolean; crop: string | null; slot_start: string | null; slot_end: string | null; m3: number; m3_delivered: number; price_rs: number; status: string; paid: boolean; channel: string };
type Cash = { paid_rs: number; due_rs: number; bookings: number; saur_mitra_share_rs: number };
type Budget = { season: string; season_cap_m3: number; used_m3: number; used_fraction: number; alert: boolean };
type Drive = { state: string; fault: string | null; fault_name: string | null; freq_hz: number; power_kw: number };
type Issue = { id: number; kind: string; note: string; status: string; at: string };
type Diag = { step?: number; of?: number; instruction_en: string; instruction_hi: string | null; done: boolean };

const T = {
  hi: { today: "आज", cash: "पैसा", alerts: "अलर्ट", fix: "मरम्मत", water: "पानी", collect: "नकद लिया", paid: "भुगतान हो गया", noSlot: "आज समय नहीं", confirm: "पक्का करें", cancel: "रहने दें", code: "कोड", due: "बाकी", got: "जमा", share: "आपका हिस्सा", offline: "इंटरनेट नहीं है: पिछला डेटा दिखा रहे हैं", nofault: "ड्राइव ठीक चल रहा है", start: "मरम्मत शुरू करें", next: "हो गया, आगे", reset: "ड्राइव रीसेट करें", budget: "भूजल बजट", fault: "फ़ॉल्ट", m3: "घन मीटर", rs: "₹", tenant: "बटाईदार", lang: "English", issues: "शिकायतें" },
  en: { today: "Today", cash: "Cash", alerts: "Alerts", fix: "Repair", water: "water", collect: "Cash received", paid: "Paid", noSlot: "no slot today", confirm: "Confirm", cancel: "Cancel", code: "Code", due: "Due", got: "Collected", share: "Your share", offline: "Offline: showing the last saved data", nofault: "Drive is running normally", start: "Start the guided fix", next: "Done, next", reset: "Reset the drive", budget: "Groundwater budget", fault: "Fault", m3: "m³", rs: "₹", tenant: "tenant", lang: "हिंदी", issues: "Complaints" },
};

export default function MitraPage() {
  const [lang, setLang] = useState<"hi" | "en">("hi");
  const t = T[lang];
  const [tab, setTab] = useState<"today" | "cash" | "alerts" | "fix">("today");
  const { data: bookings, error, reload } = useApi<Booking[]>("/api/bookings", 4000);
  const { data: budget } = useApi<Budget>("/api/budget", 8000);
  const { data: drive } = useApi<Drive>("/api/drive", 3000);
  const { data: issues } = useApi<Issue[]>("/api/issues", 8000);
  const [cashBook, setCashBook] = useState<Cash | null>(null);
  const [confirm, setConfirm] = useState<Booking | null>(null);
  const [codes, setCodes] = useState<Record<string, string>>({});
  const [diag, setDiag] = useState<Diag | null>(null);
  const [step, setStep] = useState(0);
  const [online, setOnline] = useState(true);

  useEffect(() => {
    if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
    const on = () => setOnline(navigator.onLine);
    on();
    window.addEventListener("online", on);
    window.addEventListener("offline", on);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", on);
    };
  }, []);
  useEffect(() => {
    postJSON<Cash>("/api/tools/cash_book", { args: {} }, OPERATOR_TOKEN).then(setCashBook).catch(() => {});
  }, [bookings]);

  const collect = async (b: Booking) => {
    const r = await postJSON<{ unlock_code: string }>("/api/tools/record_payment", { args: { booking_id: b.id, method: "cash" }, confirm: true }, OPERATOR_TOKEN);
    setCodes((c) => ({ ...c, [b.id]: r.unlock_code }));
    setConfirm(null);
    reload();
  };
  const ask = async (k: number) => {
    const r = await postJSON<{ diagnosis: Diag }>("/api/agents/copilot", { text: `${drive?.fault ?? ""} fault`, session_id: "mitra", step: k });
    setDiag(r.diagnosis);
    setStep(k);
  };
  const alerts = [
    ...(drive?.fault ? [{ k: "fault", text: `${t.fault} ${drive.fault}: ${drive.fault_name}`, red: true }] : []),
    ...(budget ? [{ k: "budget", text: `${t.budget}: ${Math.round(budget.used_fraction * 100)}% (${Math.round(budget.used_m3)} / ${Math.round(budget.season_cap_m3)} ${t.m3})`, red: budget.alert }] : []),
  ];

  return (
    <div className="mitra min-h-dvh md:bg-[#d9d2c1] md:py-6" lang={lang}>
    <div className="relative mx-auto min-h-dvh max-w-md bg-paper pb-24 md:min-h-[860px] md:overflow-hidden md:rounded-[32px] md:shadow-2xl">
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-ink/10 bg-paper/95 px-4 py-3 backdrop-blur">
        <div>
          <div className="deva text-[20px] font-semibold leading-tight">{lang === "hi" ? "सौर मित्र" : "Saur Mitra"}</div>
          <div className="text-[12px] text-[#3d4a43]">Pump P1 · Sunita Kumari</div>
        </div>
        <div className="flex items-center gap-2">
          <span className={`rounded-full px-2.5 py-1 text-[12px] font-medium ${drive?.fault ? "bg-fault text-white" : "bg-[#14652a] text-white"}`}>
            {drive?.fault ? drive.fault : drive?.state === "operation_enabled" ? `${drive.freq_hz.toFixed(0)} Hz` : "RDY"}
          </span>
          <button onClick={() => setLang(lang === "hi" ? "en" : "hi")} className="rounded-full border border-ink/20 px-3 py-1.5 text-[13px]">
            {t.lang}
          </button>
        </div>
      </header>
      {(!online || error) && <div role="status" className="deva bg-sun px-4 py-2 text-[14px] text-ink">{t.offline}</div>}

      <main className="mx-auto flex max-w-xl flex-col gap-3 p-4">
        {tab === "today" &&
          (bookings ?? []).map((b) => (
            <article key={b.id} className="rounded-2xl border border-ink/10 bg-white p-4 shadow-sm">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="deva text-[18px] font-semibold">{b.farmer}</div>
                  <div className="text-[13px] text-[#3d4a43]">
                    {b.crop} {b.tenant ? `· ${t.tenant}` : ""} · {b.channel}
                  </div>
                </div>
                <div className="num text-right text-[22px] font-semibold text-[#145b85]">{b.slot_start ? `${b.slot_start}–${b.slot_end}` : <span className="deva text-[14px] opacity-60">{t.noSlot}</span>}</div>
              </div>
              <div className="num mt-2 flex items-center gap-4 text-[15px]">
                <span>💧 {b.m3_delivered.toFixed(0)}/{b.m3.toFixed(0)} {t.m3}</span>
                <span>₹{b.price_rs.toFixed(0)}</span>
              </div>
              <div className="mt-3">
                {b.paid ? (
                  <div className="deva rounded-xl bg-[#e3f3e6] px-3 py-2.5 text-[15px] font-medium text-[#1d6b30]">
                    ✓ {t.paid}
                    {codes[b.id] && <span className="num ml-2">{t.code} {codes[b.id]}</span>}
                  </div>
                ) : (
                  <button onClick={() => setConfirm(b)} className="deva min-h-12 w-full rounded-xl bg-ink text-[17px] font-semibold text-paper">
                    {t.collect} ₹{b.price_rs.toFixed(0)}
                  </button>
                )}
              </div>
            </article>
          ))}

        {tab === "cash" && cashBook && (
          <section className="grid grid-cols-2 gap-3">
            {[
              [t.got, cashBook.paid_rs],
              [t.due, cashBook.due_rs],
              [t.share, cashBook.saur_mitra_share_rs],
            ].map(([k, v]) => (
              <div key={k as string} className="rounded-2xl bg-white p-4 shadow-sm">
                <div className="deva text-[14px] opacity-70">{k}</div>
                <div className="num text-[30px] font-semibold">₹{Number(v).toLocaleString("en-IN")}</div>
              </div>
            ))}
          </section>
        )}

        {tab === "alerts" && (
          <section className="flex flex-col gap-3">
            {alerts.map((a) => (
              <div key={a.k} className={`deva rounded-2xl p-4 text-[16px] ${a.red ? "bg-fault text-white" : "bg-white"}`}>{a.text}</div>
            ))}
            <h2 className="deva mt-2 text-[15px] font-semibold">{t.issues}</h2>
            {(issues ?? []).map((i) => (
              <div key={i.id} className="deva rounded-xl bg-white p-3 text-[14px]">
                <span className="num opacity-60">#{i.id} {i.at.slice(11, 16)}</span> {i.kind}: {i.note}
              </div>
            ))}
          </section>
        )}

        {tab === "fix" && (
          <section className="rounded-2xl bg-white p-5 shadow-sm">
            {!drive?.fault && !diag && <p className="deva text-[17px]">{t.nofault}</p>}
            {drive?.fault && !diag && (
              <>
                <p className="deva text-[18px] font-semibold text-fault">{t.fault} {drive.fault}: {drive.fault_name}</p>
                <button onClick={() => ask(0)} className="deva mt-4 min-h-12 w-full rounded-xl bg-ink text-[17px] font-semibold text-paper">{t.start}</button>
              </>
            )}
            {diag && (
              <div className="flex flex-col gap-3">
                <div className="num text-[13px] opacity-60">{(diag.step ?? 0) + 1} / {diag.of}</div>
                {diag.instruction_hi && <p className="deva text-[20px] leading-relaxed">{diag.instruction_hi}</p>}
                <p className={diag.instruction_hi ? "text-[14px] opacity-70" : "text-[18px]"}>{diag.instruction_en}</p>
                {!diag.done ? (
                  <button onClick={() => ask(step + 1)} className="deva min-h-12 rounded-xl bg-ink text-[17px] font-semibold text-paper">{t.next}</button>
                ) : (
                  <button
                    onClick={async () => {
                      await postJSON("/api/agents/copilot", { text: "haan", session_id: "mitra" });
                      setDiag(null);
                    }}
                    className="deva min-h-12 rounded-xl bg-[#1d8a37] text-[17px] font-semibold text-white"
                  >
                    {t.reset}
                  </button>
                )}
              </div>
            )}
          </section>
        )}
      </main>

      {confirm && (
        <div role="dialog" aria-modal="true" aria-labelledby="cfm" className="fixed inset-0 z-20 flex items-end bg-black/40 p-4 sm:items-center sm:justify-center">
          <div className="w-full max-w-md rounded-2xl bg-paper p-5">
            <p id="cfm" className="deva text-[19px]">
              {lang === "hi" ? `${confirm.farmer} से ₹${confirm.price_rs.toFixed(0)} नकद लिया?` : `Received ₹${confirm.price_rs.toFixed(0)} cash from ${confirm.farmer}?`}
            </p>
            <div className="mt-5 grid grid-cols-2 gap-3">
              <button onClick={() => setConfirm(null)} className="deva min-h-12 rounded-xl border border-ink/20 text-[16px]">{t.cancel}</button>
              <button onClick={() => collect(confirm)} className="deva min-h-12 rounded-xl bg-ink text-[16px] font-semibold text-paper">{t.confirm}</button>
            </div>
          </div>
        </div>
      )}

      <nav aria-label="Saur Mitra" className="fixed inset-x-0 bottom-0 mx-auto grid max-w-md grid-cols-4 border-t border-ink/10 bg-paper md:absolute">
        {([
          ["today", "☀", t.today],
          ["cash", "₹", t.cash],
          ["alerts", "!", t.alerts],
          ["fix", "🔧", t.fix],
        ] as const).map(([k, icon, label]) => (
          <button key={k} onClick={() => setTab(k)} aria-current={tab === k ? "page" : undefined} className={`deva flex min-h-16 flex-col items-center justify-center gap-0.5 text-[13px] ${tab === k ? "font-semibold text-ink" : "text-[#3d4a43]"}`}>
            <span className="text-[20px]" aria-hidden>{icon}</span>
            {label}
            {k === "alerts" && alerts.some((a) => a.red) && <span className="sr-only">(needs attention)</span>}
          </button>
        ))}
      </nav>
      <Link href="/twin" className="sr-only focus:not-sr-only">Dashboard</Link>
    </div>
    </div>
  );
}
