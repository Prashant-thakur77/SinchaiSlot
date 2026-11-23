"use client";

import { useEffect, useMemo, useState } from "react";

/** Text that arrives word by word, like a voice being transcribed. Splits with Intl.Segmenter so Devanagari
 *  conjuncts and matras stay whole. Reduced motion or an old browser: the full text at once. */
export function TypeOut({ text, msPerWord = 70 }: { text: string; msPerWord?: number }) {
  const words = useMemo(() => {
    const Seg = (Intl as unknown as { Segmenter?: new (l?: string, o?: { granularity: string }) => { segment: (s: string) => Iterable<{ segment: string }> } }).Segmenter;
    if (!Seg) return [text];
    return Array.from(new Seg(undefined, { granularity: "word" }).segment(text), (s) => s.segment);
  }, [text]);
  const [n, setN] = useState(0);
  // Remount with a new `key` for new text; the interval only ever advances the count.
  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const id = setInterval(() => setN((k) => (reduce ? words.length : Math.min(words.length, k + 1))), reduce ? 0 : msPerWord);
    return () => clearInterval(id);
  }, [words, msPerWord]);
  return (
    <>
      <span aria-hidden>{words.slice(0, n).join("")}</span>
      <span className="sr-only">{text}</span>
    </>
  );
}
