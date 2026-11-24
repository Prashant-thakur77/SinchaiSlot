"use client";

import { useCallback, useSyncExternalStore } from "react";

type Rec = { lang: string; interimResults: boolean; start(): void; stop(): void; onresult: ((e: { results: { transcript: string }[][] }) => void) | null; onend: (() => void) | null; onerror: ((e: { error: string }) => void) | null };
type RecCtor = new () => Rec;

const ctor = (): RecCtor | null => {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: RecCtor; webkitSpeechRecognition?: RecCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
};
// Browsers ship Hindi and Indian English only; Maithili and Bhojpuri share the script, so Hindi reads them.
const tag = (lang: string) => (lang === "en" ? "en-IN" : "hi-IN");

const subVoices = (cb: () => void) => {
  if (!("speechSynthesis" in window)) return () => {};
  window.speechSynthesis.addEventListener("voiceschanged", cb);
  return () => window.speechSynthesis.removeEventListener("voiceschanged", cb);
};
const subNone = () => () => {};

/** The viewer's own browser voices: no service, no key, nothing sent to our server as audio. */
export function useVoice(lang: string) {
  const canSpeak = useSyncExternalStore(subVoices, () => "speechSynthesis" in window && window.speechSynthesis.getVoices().some((v) => v.lang.replace("_", "-").startsWith(tag(lang).slice(0, 2))), () => false);
  const canListen = useSyncExternalStore(subNone, () => !!ctor(), () => false);
  const speak = useCallback((text: string) => {
    if (!("speechSynthesis" in window)) return;
    const want = tag(lang);
    const vs = window.speechSynthesis.getVoices().map((v) => ({ v, l: v.lang.replace("_", "-") }));
    const voice = vs.find((x) => x.l === want)?.v ?? vs.find((x) => x.l.startsWith(want.slice(0, 2)))?.v;
    if (!voice) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = want;
    u.voice = voice;
    u.rate = 0.92;
    window.speechSynthesis.speak(u);
  }, [lang]);
  const hush = useCallback(() => { if ("speechSynthesis" in window) window.speechSynthesis.cancel(); }, []);
  const listen = useCallback((onText: (t: string) => void, onEnd: (err?: string) => void) => {
    const C = ctor();
    if (!C) return () => {};
    const r = new C();
    r.lang = tag(lang);
    r.interimResults = false;
    let err: string | undefined;
    r.onresult = (e) => onText(e.results[0][0].transcript);
    r.onerror = (e) => { err = e.error; };
    r.onend = () => onEnd(err);
    r.start();
    return () => r.stop();
  }, [lang]);
  return { canSpeak, canListen, speak, hush, listen };
}
