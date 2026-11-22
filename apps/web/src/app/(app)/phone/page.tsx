"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Shell } from "@/components/Shell";
import { Btn, Panel, SourceTag } from "@/components/ui";
import { postJSON, type ServerEvent, useApi, useEvents } from "@/lib/api";
import { ToolList } from "@/components/ToolList";
import type { AgentReply } from "@/lib/types";

type Turn = { who: "farmer" | "saathi" | "system"; text: string; dtmf?: string | null };
type Farmer = { id: string; name: string; tenant: boolean; language: string };
const LANG: Record<string, string> = { mai: "Maithili", hi: "Hindi", bho: "Bhojpuri", en: "English" };

const QUICK: Record<string, string[]> = {
  mai: ["हँ, बुक करू", "नै", "कतेक लागत?", "हमर समय किएक बदलल?", "पंप बंद पड़ल अछि"],
  hi: ["हाँ", "नहीं", "कितना लगेगा?", "मेरी बुकिंग", "पानी नहीं आ रहा"],
  bho: ["हाँ, कर दीं", "ना", "केतना लागी?", "समय काहे बदलल?"],
  en: ["yes", "no", "how much?", "my booking"],
};

export default function PhonePage() {
  const { data: village } = useApi<{ farmers: Farmer[] }>("/api/village");
  const [fid, setFid] = useState("H01");
  const farmer = village?.farmers.find((f) => f.id === fid);
  const [call, setCall] = useState<{ session: string; turns: Turn[]; closed: boolean } | null>(null);
  const [last, setLast] = useState<AgentReply | null>(null);
  const [say, setSay] = useState("");
  const [wa, setWa] = useState<Turn[]>([]);
  const [waText, setWaText] = useState("");
  const [busy, setBusy] = useState(false);
  const [callbacks, setCallbacks] = useState<{ at: string; name: string; text: string; language: string }[]>([]);
  const [ringing, setRinging] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);

  const onEvent = useCallback((e: ServerEvent) => {
    if (e.kind !== "callback") return;
    const c = e as unknown as { at: string; name: string; text: string; language: string };
    setCallbacks((x) => [c, ...x].slice(0, 12));
    setRinging(true);
    setTimeout(() => setRinging(false), 2000);
  }, []);
  useEvents(onEvent, ["callback"]);
  useEffect(() => {
    scroller.current?.scrollTo({ top: 1e6, behavior: "smooth" });
  }, [call]);

  const missedCall = async () => {
    setBusy(true);
    try {
      const r = await postJSON<AgentReply & { session_id: string; transcript: { who: string; text: string }[] }>("/api/channels/ivr/missed_call", { farmer_id: fid });
      setCall({ session: r.session_id, turns: r.transcript.map((t) => ({ who: t.who as Turn["who"], text: t.text })), closed: false });
      setLast(r);
    } finally {
      setBusy(false);
    }
  };
  const answer = async (text: string | null, dtmf: string | null = null) => {
    if (!call) return;
    setBusy(true);
    try {
      const r = await postJSON<AgentReply & { transcript: { who: string; text: string; dtmf?: string }[] }>("/api/channels/ivr/say", {
        session_id: call.session,
        text,
        dtmf,
      });
      setCall({ session: call.session, turns: r.transcript.map((t) => ({ who: t.who as Turn["who"], text: t.text, dtmf: t.dtmf })), closed: !!r.closed });
      setLast(r);
      setSay("");
    } finally {
      setBusy(false);
    }
  };
  const sendWa = async (text: string) => {
    if (!text.trim()) return;
    setBusy(true);
    try {
      const r = await postJSON<AgentReply & { transcript: { who: string; text: string }[] }>("/api/channels/whatsapp", { farmer_id: fid, text });
      setWa(r.transcript.map((t) => ({ who: t.who as Turn["who"], text: t.text })));
      setLast(r);
      setWaText("");
    } finally {
      setBusy(false);
    }
  };

  const lang = farmer?.language ?? "hi";
  return (
    <Shell title="Saathi: farmer phone">
      <div className="mb-4 flex flex-wrap items-center gap-3 text-[13px]">
        <label className="flex items-center gap-2">
          Farmer
          <select value={fid} onChange={(e) => { setFid(e.target.value); setCall(null); setWa([]); setLast(null); }} className="rounded border border-soil bg-night-2 px-2 py-1.5">
            {(village?.farmers ?? []).map((f) => (
              <option key={f.id} value={f.id}>
                {f.name} {f.tenant ? "(tenant)" : ""} · {LANG[f.language] ?? f.language}
              </option>
            ))}
          </select>
        </label>
        <span className="text-mist">Speech is simulated as text in the demo (no paid speech service needed). <SourceTag kind="simulated" /></span>
      </div>
      <div className="grid gap-5 xl:grid-cols-[320px_320px_minmax(0,1fr)]">
        {/* Feature phone */}
        <div className="mx-auto w-[300px]">
          <div className={`rounded-[36px] border-[10px] border-[#26302b] bg-[#1a221e] p-3 shadow-2xl ${ringing ? "ringing" : ""}`}>
            <div className="rounded-[10px] bg-[#c9d6a8] p-2 text-ink">
              <div className="flex justify-between text-[10px] opacity-70">
                <span>Jio 4G</span>
                <span>{call && !call.closed ? "On call" : "Idle"}</span>
              </div>
              <div ref={scroller} className="deva mt-1 h-[260px] space-y-2 overflow-y-auto text-[13px] leading-snug" aria-live="polite" lang={lang}>
                {!call && (
                  <p className="pt-16 text-center text-[13px]">
                    {farmer?.name ?? "…"}
                    <br />
                    <span className="text-[11px] opacity-70">Give a missed call to the pump number. It is free; Saathi calls back.</span>
                  </p>
                )}
                {call?.turns.map((t, i) => (
                  <p key={i} className={t.who === "farmer" ? "text-right font-medium" : t.who === "system" ? "text-center text-[11px] opacity-60" : ""}>
                    {t.who === "farmer" && t.dtmf ? `[${t.dtmf}] ` : ""}
                    {t.text}
                  </p>
                ))}
              </div>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <button onClick={missedCall} disabled={busy} className="rounded-full bg-leaf py-2 text-[13px] font-medium text-ink disabled:opacity-50">
                Missed call
              </button>
              <button onClick={() => setCall(null)} className="rounded-full bg-[#3b4540] py-2 text-[13px] font-medium text-white">
                Hang up
              </button>
            </div>
            <div className="mt-2 grid grid-cols-3 gap-1.5" role="group" aria-label="Keypad">
              {["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"].map((k) => (
                <button key={k} disabled={!call || call.closed || busy} onClick={() => answer(null, k)} className="num rounded-md bg-[#2b3631] py-2 text-[15px] text-white disabled:opacity-50">
                  {k}
                </button>
              ))}
            </div>
          </div>
          <form
            className="mt-3 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (say.trim()) answer(say);
            }}
          >
            <input value={say} onChange={(e) => setSay(e.target.value)} disabled={!call || call.closed} placeholder="Speak (type what the farmer says)" aria-label="Farmer speaks" className="deva min-w-0 flex-1 rounded-md border border-soil bg-night-2 px-2 py-1.5 text-[13px]" />
            <Btn type="submit" disabled={!call || call.closed || busy}>Say</Btn>
          </form>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {(QUICK[lang] ?? QUICK.hi).map((q) => (
              <button key={q} disabled={!call || call.closed || busy} onClick={() => answer(q)} className="deva rounded-full border border-soil px-2.5 py-0.5 text-[12px] text-fog hover:bg-night-2 disabled:opacity-40">
                {q}
              </button>
            ))}
          </div>
        </div>

        {/* WhatsApp */}
        <div className="mx-auto flex h-[560px] w-[300px] flex-col overflow-hidden rounded-[28px] border-[8px] border-[#26302b] bg-[#0b141a]">
          <div className="flex items-center gap-2 bg-[#1f2c33] px-3 py-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-sun font-display text-ink">स</div>
            <div className="text-[13px]">
              <div className="font-medium">SinchaiSlot Saathi</div>
              <div className="text-[11px] text-mist">WhatsApp (simulated)</div>
            </div>
          </div>
          <div className="deva flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-3 text-[13px]" lang={lang} aria-live="polite">
            {wa.length === 0 && <p className="mt-20 text-center text-[12px] text-mist">Text or voice note to Saathi. Try “kitna lagega?”</p>}
            {wa.map((t, i) => (
              <div key={i} className={`max-w-[85%] rounded-lg px-2.5 py-1.5 ${t.who === "farmer" ? "self-end bg-[#005c4b]" : "self-start bg-[#1f2c33]"}`}>
                {t.text}
              </div>
            ))}
          </div>
          <form className="flex gap-2 bg-[#1f2c33] p-2" onSubmit={(e) => { e.preventDefault(); sendWa(waText); }}>
            <input value={waText} onChange={(e) => setWaText(e.target.value)} placeholder="Message" aria-label="WhatsApp message" className="deva min-w-0 flex-1 rounded-full bg-[#2a3942] px-3 py-1.5 text-[13px] outline-none" />
            <button type="submit" disabled={busy} className="rounded-full bg-[#00a884] px-3 text-[13px] text-ink">Send</button>
          </form>
        </div>

        {/* Agent view */}
        <div className="flex min-w-0 flex-col gap-4">
          <Panel title="What Saathi did on the last turn" right={last && <span className="num text-[11px] text-mist">{last.provider} · {last.latency_ms} ms</span>}>
            {!last && <p className="text-sm text-mist">Every tool call is typed and logged. Anything that spends money or water waits for the farmer&apos;s yes.</p>}
            {last && (
              <div className="flex flex-col gap-3">
                {last.pending && (
                  <div className="rounded-md border border-sun/60 bg-sun/10 px-3 py-2 text-[13px] text-sun">
                    Waiting for confirmation: <code className="num">{last.pending.tool}</code> (nothing is booked until the farmer says yes)
                  </div>
                )}
                <ToolList calls={last.tool_calls} />
              </div>
            )}
          </Panel>
          <Panel title="Plan-change calls" right={<span className="text-[11px] text-mist">sent when the planner moves a slot</span>}>
            {callbacks.length === 0 && <p className="text-sm text-mist">None yet. Use “Jump to 13:45” in the top bar: the cloud moves slots and Saathi calls each affected farmer.</p>}
            <ul className="deva flex flex-col gap-2 text-[13px]">
              {callbacks.map((c, i) => (
                <li key={i} className="rounded-md border border-soil p-2.5">
                  <div className="num text-[11px] text-mist">{c.at} · {c.name} · {LANG[c.language] ?? c.language}</div>
                  <div>{c.text}</div>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      </div>
    </Shell>
  );
}
