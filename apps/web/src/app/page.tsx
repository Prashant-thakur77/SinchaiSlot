"use client";

import Link from "next/link";
import { area, curveMonotoneX, line } from "d3-shape";
import { useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { Border, Motif, VillageScene } from "@/components/Art";
import type { PlotFeature } from "@/components/PlotMosaic";
import { Receipt } from "@/components/Receipt";
import { Mark, NAV } from "@/components/Shell";
import { SourceTag } from "@/components/ui";
import { fmt, getJSON } from "@/lib/api";
import type { LedgerRow, Proof } from "@/lib/types";

type Motion = { gsap: typeof import("gsap").gsap; ScrollTrigger: typeof import("gsap/ScrollTrigger").ScrollTrigger; Lenis: typeof import("lenis").default };

/** Animation libraries load after the page is painted and interactive; the content never waits on them. */
async function loadMotion(): Promise<Motion> {
  const [g, st, l] = await Promise.all([import("gsap"), import("gsap/ScrollTrigger"), import("lenis")]);
  g.gsap.registerPlugin(st.ScrollTrigger);
  return { gsap: g.gsap, ScrollTrigger: st.ScrollTrigger, Lenis: l.default };
}

const PlotMosaic = dynamic(() => import("@/components/PlotMosaic").then((m) => m.PlotMosaic), { ssr: false });

type Constants = Record<string, { value: number; unit: string; kind: string; source: string | null }>;
type Story = {
  day: string;
  offer: { mai: string; en: string; greet: string } | null;
  callbacks: { name: string; language: string; text: string; at: string }[];
  receipt: LedgerRow | null;
  replay: {
    label: string;
    callbacks: { name: string; language: string; text: string; at: string }[];
    slots_before: { start: string; action: string; farmer: string | null }[];
    slots_after: { start: string; action: string; farmer: string | null }[];
  } | null;
};

const SLOT_CLS: Record<string, string> = { req: "bg-water", mill: "bg-sun", chaff: "bg-chaff", battery: "bg-mist/70", idle: "bg-ink/[.08]" };

const FARMER_SHADES = ["bg-water", "bg-[#a9d3dc]", "bg-water-deep", "bg-[#cfe6ea]"];

function SlotStrip({ slots, order, className = "" }: { slots: { start: string; action: string; farmer: string | null }[]; order: string[]; className?: string }) {
  return (
    <div className={`grid h-5 grid-cols-24 gap-px ${className}`} style={{ gridTemplateColumns: `repeat(${slots.length}, minmax(0, 1fr))` }}>
      {slots.map((s, i) => {
        const prev = slots[i - 1];
        const head = s.action === "req" && (!prev || prev.farmer !== s.farmer || prev.action !== "req");
        return (
          <div key={s.start} title={`${s.start} ${s.action === "req" ? s.farmer : s.action}`}
            className={`relative rounded-[2px] ${s.action === "req" ? FARMER_SHADES[Math.max(0, order.indexOf(s.farmer ?? "")) % FARMER_SHADES.length] : SLOT_CLS[s.action] ?? "bg-soil"}`}>
            {head && <span className="absolute -top-4 left-0 hidden whitespace-nowrap text-[12px] text-fog md:block">{s.farmer?.split(" ")[0]}</span>}
          </div>
        );
      })}
    </div>
  );
}

export default function Home() {
  const root = useRef<HTMLDivElement>(null);
  const [proof, setProof] = useState<Proof | null>(null);
  const [c, setC] = useState<Constants | null>(null);
  const [story, setStory] = useState<Story | null>(null);
  const [plots, setPlots] = useState<PlotFeature[]>([]);
  const [motion, setMotion] = useState<Motion | null>(null);
  const skyRef = useRef<HTMLDivElement>(null);
  const sunRef = useRef<SVGCircleElement>(null);
  const hudRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let live = true;
    loadMotion().then((m) => live && setMotion(m)).catch(() => {});
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    getJSON<Proof>("/api/proof").then(setProof).catch(() => {});
    getJSON<Constants>("/api/constants").then(setC).catch(() => {});
    getJSON<Story>("/api/story").then(setStory).catch(() => {});
    getJSON<{ plots: { features: PlotFeature[] } }>("/api/village").then((v) => setPlots(v.plots.features)).catch(() => {});
  }, []);

  // Smooth scroll (off for reduced motion), driven by GSAP's ticker so ScrollTrigger stays in sync.
  useEffect(() => {
    if (!motion) return;
    const { gsap, ScrollTrigger, Lenis } = motion;
    const lenis = new Lenis({ lerp: 0.09 });
    lenis.on("scroll", ScrollTrigger.update);
    const raf = (t: number) => lenis.raf(t * 1000);
    gsap.ticker.add(raf);
    gsap.ticker.lagSmoothing(0);
    return () => {
      gsap.ticker.remove(raf);
      lenis.destroy();
    };
  }, [motion]);

  useEffect(() => {
    if (!motion) return;
    const { gsap } = motion;
    const ctx = gsap.context(() => {
      const mm = gsap.matchMedia();
      // The whole page is one day: scroll position is the clock; the sky and the sun follow it.
      const dayKw = proof?.demo_day?.pv_actual_kw ?? [];
      const cum: number[] = [0];
      dayKw.forEach((k, i) => cum.push(cum[i] + k));
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        gsap.to(".scene-sun", { y: 40, ease: "none", scrollTrigger: { trigger: ".hero", start: "top top", end: "bottom top", scrub: true } });
        let progress = 0;
        motion.ScrollTrigger.create({ start: 0, end: "max", onUpdate: (self) => { progress = self.progress; } });
        // Repaint every frame: the pinned chapter's clock eases after the scroll, and the nav clock reads it.
        const tick = () => paintSky(progress, skyRef.current, sunRef.current, hudRef.current, cum);
        gsap.ticker.add(tick);
        tick();
        return () => gsap.ticker.remove(tick);
      });
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        // Hero: the sun rises as you start scrolling; the wordmark settles.
        // 06:00 statement fills word by word.
        gsap.fromTo(".fill-word", { color: "#8a7d5c" }, { color: "#2b2a1b", stagger: 0.08, ease: "none", scrollTrigger: { trigger: ".problem", start: "top 70%", end: "bottom 60%", scrub: true } });
        // The beam: a wedge of morning sun sweeps across and becomes the gold chapter.
        gsap.fromTo(
          ".beam",
          { clipPath: "polygon(0% 0%, 0% 0%, 0% 0%)" },
          { clipPath: "polygon(0% 0%, 260% 0%, 0% 260%)", ease: "none", scrollTrigger: { trigger: ".beam-wrap", start: "top 85%", end: "top 15%", scrub: true } },
        );
        gsap.from(".phone-card", { y: 80, rotate: -4, opacity: 0, duration: 1.1, ease: "expo.out", scrollTrigger: { trigger: ".beam-wrap", start: "top 40%" } });
        // Signature: the real day's sun draws across the screen; the cloud passes at 13:40.
        const tl = gsap.timeline({ scrollTrigger: { trigger: ".day", start: "top top", end: "+=260%", scrub: 0.6, pin: true } });
        tl.fromTo(".curve-actual", { strokeDashoffset: 1 }, { strokeDashoffset: 0, ease: "none", duration: 1 }, 0)
          .fromTo(".curve-band", { opacity: 0 }, { opacity: 0.26, duration: 0.25 }, 0)
          .fromTo(".curve-p50", { strokeDashoffset: 1 }, { strokeDashoffset: 0, ease: "none", duration: 1 }, 0)
          .fromTo(".day-clock", { innerText: "06" }, { innerText: 18, snap: { innerText: 1 }, ease: "none", duration: 1, onUpdate() { const el = document.querySelector(".day-clock"); if (el) el.textContent = String(el.textContent).padStart(2, "0"); } }, 0)
          .fromTo(".cloud", { xPercent: -120, opacity: 0 }, { xPercent: 40, opacity: 1, duration: 0.3 }, 0.55)
          .to(".cloud", { xPercent: 140, opacity: 0, duration: 0.25 }, 0.85)
          .fromTo(".cloud-note", { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.12 }, 0.62)
          .fromTo(".ring-card", { opacity: 0, y: 40 }, { opacity: 1, y: 0, duration: 0.12 }, 0.7)
          .fromTo(".strip-before", { opacity: 1 }, { opacity: 0, duration: 0.08 }, 0.62)
          .fromTo(".strip-after", { opacity: 0, clipPath: "inset(-24px 0 0 64%)" }, { opacity: 1, clipPath: "inset(-24px 0 0 0%)", duration: 0.12, ease: "power2.out" }, 0.62)
          .fromTo(".ring-dot", { scale: 1 }, { scale: 1.6, repeat: 5, yoyo: true, duration: 0.02 }, 0.72);
        // Receipt prints at dusk.
        gsap.fromTo(".receipt-slot", { clipPath: "inset(0 0 100% 0)" }, { clipPath: "inset(0 0 0% 0)", ease: "power2.out", scrollTrigger: { trigger: ".dusk", start: "top 60%", end: "top 10%", scrub: true } });
        // Proof numbers count up once.
        gsap.utils.toArray<HTMLElement>(".count").forEach((el) => {
          const to = Number(el.dataset.to);
          const dec = Number(el.dataset.dec ?? 0);
          if (!Number.isFinite(to)) return;
          const o = { v: 0 };
          gsap.to(o, { v: to, duration: 1.4, ease: "power3.out", scrollTrigger: { trigger: el, start: "top 85%", once: true }, onUpdate: () => { el.textContent = o.v.toLocaleString("en-IN", { maximumFractionDigits: dec, minimumFractionDigits: dec }); } });
        });
      });
    }, root);
    return () => ctx.revert();
  }, [motion, proof, story, plots.length]);

  const day = proof?.demo_day;
  const chart = useMemo(() => {
    if (!day) return null;
    const W = 1600, H = 520, n = day.slots.length;
    const max = Math.max(...day.pv_q90_kw) * 1.15;
    const X = (i: number) => (i / (n - 1)) * W;
    const Y = (v: number) => H - (v / max) * (H - 40);
    const idx = day.slots.map((_, i) => i);
    const smooth = (a: number[]) => line<number>().x(X).y((i) => Y(a[i])).curve(curveMonotoneX)(idx) ?? "";
    const band = area<number>().x(X).y0((i) => Y(day.pv_q10_kw[i])).y1((i) => Y(day.pv_q90_kw[i])).curve(curveMonotoneX)(idx) ?? "";
    // Hour index of the largest shortfall below P10 in the afternoon.
    let worst = 7, gap = -1;
    for (let i = 6; i < n - 2; i++) {
      const g = day.pv_q10_kw[i] - day.pv_actual_kw[i];
      if (g > gap) {
        gap = g;
        worst = i;
      }
    }
    return { W, H, band, actual: smooth(day.pv_actual_kw), p50: smooth(day.pv_q50_kw), cloudX: X(worst), cloudY: Y(day.pv_actual_kw[worst]) };
  }, [day]);

  const h = proof?.headline;
  const pol = proof?.policies;
  const ceew = c?.ceew_solar_pump_utilisation;
  const dieselRate = c?.diesel_water_rs_per_hour;
  const dieselShare = c?.bihar_diesel_structures_share;

  return (
    <div ref={root} className="relative overflow-x-clip bg-night text-ink">
      <div ref={skyRef} className="pointer-events-none fixed inset-0 z-0" aria-hidden />

      <a href="#story" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-sun focus:px-3 focus:py-1 focus:text-ink">Skip to the story</a>
      <header className="fixed inset-x-0 top-0 z-30 flex items-center justify-between border-b border-soil/60 bg-night/85 px-5 py-3 backdrop-blur-md md:px-10">
        <Link href="/" className="flex items-center gap-2 text-ink"><Mark /> <span className="font-display text-lg font-medium">SinchaiSlot</span></Link>
<div ref={hudRef} className="num pointer-events-none hidden items-center gap-3 text-[12px] text-mist lg:motion-safe:flex" aria-hidden>
        <svg width="64" height="26" viewBox="0 0 64 26" className="overflow-visible">
          <path d="M4 24 Q32 -8 60 24" fill="none" stroke="var(--soil)" strokeWidth="1.5" strokeDasharray="2 3" />
          <line x1="0" x2="64" y1="24" y2="24" stroke="var(--soil)" strokeWidth="1" />
          <circle ref={sunRef} cx="4" cy="24" r="4.5" fill="var(--sun)" />
        </svg>
        <span data-hud="clock" className="text-[15px] text-sun-ink">06:00</span><span data-hud="kwh">0.0 kWh of real sun so far</span>
      </div>
        <nav className="flex items-center gap-5 text-[13px] text-ink">
          <a href="#proof" className="hidden hover:underline sm:inline">Proof</a>
          <a href="#schneider" className="hidden hover:underline sm:inline">Schneider inside</a>
          <Link href="/twin" className="rounded-full border border-ink/70 px-4 py-1.5 hover:bg-ink hover:text-paper">See today live</Link>
        </nav>
      </header>

      {/* HERO */}
      <section className="hero relative z-10 flex min-h-[100svh] flex-col overflow-hidden bg-gradient-to-b from-[#f9dfa8] via-night to-night" aria-label="Introduction">
        <div className="relative z-10 mx-auto w-full max-w-[1240px] px-5 pt-28 md:px-10 md:pt-[max(5.2rem,14vh)]">
          <h1 className="max-w-[17ch] font-display text-[clamp(2.3rem,min(5vw,8.2vh),4.4rem)] max-md:text-[clamp(2.1rem,9.6vw,2.8rem)] font-medium leading-[1.04]">
            One solar pump, shared well, waters a whole village.
          </h1>
          <p className="mt-5 max-w-[46ch] text-[17px] leading-relaxed text-fog md:text-[19px]">
            SinchaiSlot plans each day of sun: water first for the farmers who book it, then the mill and batteries with what is left.
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            <Link href="/twin" className="rounded-full bg-ink px-6 py-3 text-[16px] font-medium text-paper hover:bg-fog">See today live</Link>
            <a href="#story" className="rounded-full border border-ink/40 px-6 py-3 text-[16px] hover:bg-ink/5">Follow one day</a>
          </div>
        </div>
        <VillageScene className="mt-6 h-[46svh] w-full flex-1 md:absolute md:inset-x-0 md:bottom-0 md:mt-0 md:h-[74svh]" />
      </section>
      <Border className="relative z-10" id="bd-hero" />

      {/* 06:00 PROBLEM */}
      <section id="story" className="problem relative z-10 mx-auto max-w-[1400px] px-5 py-[15vh] md:px-10" aria-labelledby="t-problem">
        <Clock t="06:00" label="Dawn, Samastipur" />
        <h2 id="t-problem" className="mt-8 max-w-5xl font-display text-[clamp(1.9rem,4vw,3.6rem)] font-medium leading-[1.14] ">
          {`Solar pumps put about ${ceew ? Math.round(ceew.value * 100) : "…"}% of their sunshine to work. Next door, a tenant farmer pays a diesel seller ₹${dieselRate?.value ?? "…"} an hour for the same water.`
            .split(" ")
            .map((w, i) => <span key={i} className="fill-word">{w} </span>)}
        </h2>
        <div className="mt-10 grid max-w-4xl gap-6 text-[15px] text-fog sm:grid-cols-3">
          <p>
            <span className="num text-2xl text-fog">{ceew ? fmt.pct(ceew.value) : "…"}</span><br />of solar pump energy used (1,131 pumps, Chhattisgarh) <SourceTag kind="published" />
          </p>
          <p>
            <span className="num text-2xl text-fog">{dieselShare ? fmt.pct(dieselShare.value) : "…"}</span><br />of Bihar&apos;s groundwater structures run on diesel <SourceTag kind="published" />
          </p>
          <p>
            <span className="num text-2xl text-fog">₹{dieselRate?.value ?? "…"}/h</span><br />diesel water in Chakhaji, Samastipur, against ₹{c?.solar_water_rs_per_hour?.value ?? "…"}/h solar <SourceTag kind="published" />
          </p>
        </div>
      </section>

      {/* 10:00 THE BEAM */}
      <section className="beam-wrap relative z-10 min-h-[80vh]" aria-labelledby="t-book">
        <div className="beam absolute inset-0 bg-[#f3c469]" style={{ clipPath: "polygon(0% 0%, 100% 0%, 100% 100%, 0% 100%)" }} aria-hidden />
        <div className="relative mx-auto grid max-w-[1400px] items-center gap-10 px-5 py-[12vh] text-ink md:grid-cols-[1.1fr_0.9fr] md:px-10">
          <div>
            <Motif name="parrot" size={120} />
            <div className="mt-6"><Clock t="10:00" label="Ramesh gives a missed call" dark /></div>
            <h2 id="t-book" className="mt-8 font-display text-[clamp(1.8rem,3.6vw,3.2rem)] font-medium leading-[1.14] ">
              The call is free. Saathi calls back in Maithili, already knowing what his wheat needs.
            </h2>
            <p className="mt-6 max-w-xl text-[16px] leading-relaxed">
              The booking is sized to the crop by the FAO-56 water balance on today&apos;s weather, so nobody books more than the field can use.
              Saathi reads the offer back and books only after he says yes. Price per cubic metre, under diesel.
            </p>
          </div>
          <div className="phone-card mx-auto w-full max-w-sm rounded-[28px] border-2 border-ink bg-paper p-5 text-ink shadow-[8px_8px_0_rgba(43,42,27,.16)]">
            <div className="flex items-center justify-between text-[12px] text-mist"><span>Saathi · callback</span><span className="num">{story?.day ?? ""}</span></div>
            <p className="deva mt-4 text-[17px] leading-relaxed" lang="mai">{story?.offer ? `${story.offer.greet} ${story.offer.mai}` : "…"}</p>
            <p className="mt-4 border-t border-ink/15 pt-3 text-[13px] leading-relaxed text-fog">{story?.offer?.en}</p>
            <div className="mt-4 flex gap-2 text-[13px]">
              <span className="rounded-full bg-sun px-3 py-1 font-medium text-ink">1 · हँ</span>
              <span className="rounded-full border border-ink/30 px-3 py-1">2 · नै</span>
            </div>
            <p className="mt-3 text-[13px] text-mist">Live from the planner on the demo day. Voice simulated as text.</p>
          </div>
        </div>
      </section>

      {/* 13:40 THE CLOUD (signature) */}
      <section className="day relative z-10 flex h-[100svh] min-h-[600px] flex-col justify-center overflow-hidden pb-6 pt-28 md:pb-8 md:pt-24" aria-labelledby="t-cloud">
        {plots.length > 0 && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center opacity-[0.07]" aria-hidden>
            <div className="w-[120vmin]"><PlotMosaic features={plots} /></div>
          </div>
        )}
        <div className="cloud pointer-events-none absolute top-[10%] h-[60vh] w-[70vw] rounded-full bg-[radial-gradient(closest-side,rgba(120,134,138,.6),rgba(120,134,138,0))]" aria-hidden />
        <div className="relative mx-auto w-full max-w-[1400px] px-5 md:px-10">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <Clock t="13:40" label="The day replays: watch the cloud arrive at 13:40" />
              <h2 id="t-cloud" className="mt-4 max-w-3xl font-display text-[clamp(1.5rem,3vw,2.8rem)] font-medium leading-[1.14] ">
                The forecast said sun. The sky said otherwise. The plan moves before the water stops.
              </h2>
            </div>
            <div className="text-left md:text-right">
              <div className="num text-[clamp(2.6rem,6vw,5.5rem)] leading-none text-sun-ink"><span className="day-clock">18</span>:00</div>
              <div className="text-[12px] text-mist">{day?.date} · real sun, held-out day <SourceTag kind="real" /></div>
            </div>
          </div>
          {chart && (
            <div className="mt-6">
              <div className="relative">
              <svg viewBox={`0 0 ${chart.W} ${chart.H}`} preserveAspectRatio="none" className="aspect-[3/1] w-full overflow-visible md:aspect-auto md:h-[30vh]" role="img" aria-label="Solar power on the demo day: forecast band, forecast median and actual">
                <path className="curve-band" d={chart.band} fill="var(--sun)" opacity="0.26" />
                <path className="curve-p50" d={chart.p50} pathLength={1} strokeDasharray="1" fill="none" stroke="var(--sun-deep)" strokeWidth="3" strokeOpacity="0.8" vectorEffect="non-scaling-stroke" />
                <path className="curve-actual" d={chart.actual} pathLength={1} strokeDasharray="1" fill="none" stroke="var(--ink)" strokeWidth="4" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
              </svg>
              <div className="cloud-note pointer-events-none absolute flex items-center gap-2" style={{ left: `${(chart.cloudX / chart.W) * 100}%`, top: `${(chart.cloudY / chart.H) * 100}%`, transform: chart.cloudX / chart.W > 0.6 ? "translate(calc(-100% + 7px), -7px)" : "translate(-7px, -7px)", flexDirection: chart.cloudX / chart.W > 0.6 ? "row-reverse" : "row" }}>
                <span className="h-3.5 w-3.5 rounded-full bg-water ring-4 ring-water/25" />
                <span className="hidden whitespace-nowrap rounded bg-night/80 px-2 py-0.5 text-[13px] text-water-ink md:inline">actual sun below the P10 forecast</span>
              </div>
              </div>
              {story?.replay && (
                <div role="img" className="relative mt-7" aria-label="Pump plan for the day, before and after the 13:40 re-plan">
                  {(() => {
                    const order = [...new Set([...story.replay.slots_before, ...story.replay.slots_after].filter((s) => s.action === "req").map((s) => s.farmer ?? ""))];
                    return (
                      <>
                        <SlotStrip slots={story.replay.slots_before} order={order} className="strip-before" />
                        <SlotStrip slots={story.replay.slots_after} order={order} className="strip-after absolute inset-0" />
                      </>
                    );
                  })()}
                </div>
              )}
              <div className="mt-2 flex flex-wrap gap-4 text-[12px] text-mist">
                <span><span className="mr-1.5 inline-block h-2 w-5 bg-sun/30 align-middle" />P10 to P90 forecast</span>
                <span><span className="mr-1.5 inline-block w-5 border-t-2 border-sun-deep align-middle" />P50</span>
                <span><span className="mr-1.5 inline-block w-5 border-t-[3px] border-ink align-middle" />actual sun</span>
                {story?.replay && <span><span className="mr-1.5 inline-block h-2 w-5 bg-water align-middle" />water slots, re-planned at 13:40</span>}
              </div>
            </div>
          )}
          <div className="mt-5 grid gap-5 md:grid-cols-[1fr_minmax(0,380px)]">
            <p className="max-w-2xl text-[16px] leading-relaxed text-fog">
              Water still comes first and the mill waits. Every farmer whose time moved gets a call in their own language, and whoever is left
              short goes first tomorrow.
            </p>
            <div className="ring-card rounded-2xl border border-water/40 bg-night-2 p-4">
              {(() => {
                const live = story?.callbacks?.length ? story.callbacks : null;
                const list = live ?? story?.replay?.callbacks ?? [];
                const last = list[list.length - 1];
                return last ? (
                  <>
                    <div className="num flex items-center gap-2 text-[12px] text-water-ink">
                      <span className="ring-dot inline-block h-2.5 w-2.5 rounded-full bg-water" aria-hidden />
                      Saathi calls · {last.at} · {last.name}
                      {!live && <SourceTag kind="simulated" className="ml-auto" />}
                    </div>
                    <p className="deva mt-2 text-[15px]" lang="mai">{last.text}</p>
                    {list.length > 1 && <p className="mt-2 text-[12px] text-mist">{list.length} farmers called about the change, each in their own language.</p>}
                  </>
                ) : (
                  <>
                    <div className="text-[12px] text-water-ink">Plan-change calls</div>
                    <p className="mt-2 text-[14px] text-fog">Run the day in the Village Twin to hear who gets called, and what they are told.</p>
                    <Link href="/twin" className="mt-3 inline-block text-[13px] text-sun-ink underline">Open the live day</Link>
                  </>
                );
              })()}
            </div>
          </div>
        </div>
      </section>

      {/* 18:00 DUSK RECEIPT */}
      <section className="dusk relative z-10 py-[12vh]" aria-labelledby="t-receipt">
        <div className="mx-auto grid max-w-[1400px] items-center gap-12 px-5 md:grid-cols-2 md:px-10">
          <div>
            <Motif name="fish" size={120} />
            <div className="mt-6"><Clock t="18:00" label="The pump stops; the books close" /></div>
            <h2 id="t-receipt" className="mt-8 font-display text-[clamp(1.8rem,3.6vw,3.2rem)] font-medium leading-[1.14] ">
              Every booking leaves a receipt a funder can pay against.
            </h2>
            <p className="mt-6 max-w-xl text-[17px] leading-relaxed text-fog">
              Litres, kilowatt-hours, diesel and CO₂ avoided, read from the drive and chained by hash to the receipt before it. Edit one and the
              chain breaks. Receipts become CSR claims, a lender&apos;s credit file, and, with a rule change, the state diesel subsidy.
            </p>
          </div>
          <div className="receipt-slot mx-auto w-full max-w-sm">{story?.receipt && <Receipt r={story.receipt} />}</div>
        </div>
      </section>

      {/* PROOF */}
      <section id="proof" className="relative z-10 mx-auto max-w-[1400px] px-5 py-[14vh] md:px-10" aria-labelledby="t-proof">
        <div className="flex flex-wrap items-baseline justify-between gap-4">
          <h2 id="t-proof" className="font-display text-[clamp(1.8rem,3.6vw,3.2rem)] font-medium ">The proof</h2>
          <p className="max-w-xl text-[13px] text-mist">
            {proof ? `${proof.setup.runs_per_policy} simulated years per policy on real NASA POWER weather (${proof.setup.years.join(", ")}, held out), real archived forecasts, ${proof.setup.seeds} synthetic villages. Bands are P10 to P90.` : "Loading reports/proof.json…"}{" "}
            <SourceTag kind="simulated" />
          </p>
        </div>
        {h && pol && (
          <ol className="mt-12 border-t border-dashed border-fog/25">
            <Row what="Sun put to work" to={h.utilisation_D_kwh_per_kwp} unit="kWh per kWp a year" base={`first-come hourly sales: ${fmt.n(h.utilisation_B_kwh_per_kwp)}`} />
            <Row what="More solar used" to={h.utilisation_gain_vs_B * 100} prefix="+" unit="%" base={`P10 ${fmt.signedPct(proof!.gains.utilisation_D_vs_B.p10)} to P90 ${fmt.signedPct(proof!.gains.utilisation_D_vs_B.p90)} across runs`} />
            <Row what="Farmer pays" to={h.farmer_rs_per_m3_D} dec={2} prefix="₹" unit="per m³" base={`baseline ₹${h.farmer_rs_per_m3_B.toFixed(2)} · diesel ₹${h.diesel_rs_per_m3.toFixed(2)}`} tone="text-water-ink" />
          </ol>
        )}
        {h && pol && (
          <details className="mt-4">
            <summary className="cursor-pointer py-2 text-[16px] underline underline-offset-4">Three more measurements</summary>
            <ol className="mt-2 border-t border-dashed border-fog/25">
            <Row what="Tenants' need met by solar" to={h.tenant_share_D * 100} unit="%" base={`baseline ${fmt.pct(h.tenant_share_B)} · Gini ${h.gini_D.toFixed(2)} vs ${h.gini_B.toFixed(2)}`} />
            <Row what="Diesel avoided" to={h.diesel_l_avoided_D} unit="litres a year" base={`${fmt.n(h.co2_kg_avoided_D)} kg CO₂ at 2.6444 kg/L`} />
            <Row what="Forecast skill" to={h.forecast_skill_vs_persistence * 100} unit="% over yesterday's sun" base={`held-out ${proof!.forecast.test_years.join("–")} · ${fmt.pct(h.forecast_skill_vs_climatology)} over climatology`} />
            </ol>
          </details>
        )}
        {proof?.negative_results?.explanation && (
          <div className="mt-14 max-w-3xl border-l-2 border-sun/60 pl-5">
            <div className="text-[13px] text-sun-ink">What the planner does not add</div>
            <p className="mt-2 font-serif text-[19px] leading-relaxed text-fog">{proof.negative_results.explanation}</p>
          </div>
        )}
        <Link href="/lab" className="mt-10 inline-block rounded-full border border-fog/40 px-5 py-2.5 text-[14px] hover:bg-ink/5">Every number, every band, every ablation →</Link>
      </section>

      <Border className="relative z-10" id="bd-se" />
      {/* SCHNEIDER */}
      <section id="schneider" className="relative z-10 bg-night-2" aria-labelledby="t-se">
        <div className="mx-auto max-w-[1400px] px-5 py-[12vh] md:px-10">
          <h2 id="t-se" className="font-display text-[clamp(1.8rem,4vw,3.4rem)] font-medium ">
            Remove the <span className="text-se-ink">Altivar Solar</span> drive and nothing works.
          </h2>
          <ol className="relative mt-12 grid gap-10 md:grid-cols-3 md:gap-0">
            <div className="absolute left-[7px] top-2 bottom-2 w-[2px] bg-gradient-to-b from-se via-sun to-water md:left-0 md:right-0 md:top-[7px] md:bottom-auto md:h-[2px] md:w-auto md:bg-gradient-to-r" aria-hidden />
            {[
              ["Connected product", "Altivar Solar ATV320", "Actuator and meter. The plan becomes start, stop and speed over Modbus; frequency and power become water, with a flow meter only to calibrate. Fault codes drive the Copilot.", "bg-se"],
              ["Edge control", "SinchaiSlot Edge", "ESP32 or Linux beside the drive. Holds tomorrow's plan offline, checks unlock codes, meters each booking, enforces the water budget and the dry-run cut-off.", "bg-sun"],
              ["Apps and analytics", "Planner · Saathi · Rasid", "Forecast and stochastic optimiser, the farmer voice agent, verified receipts, the groundwater guard and the funder ledger.", "bg-water"],
            ].map(([layer, name, text, dot]) => (
              <li key={layer} className="relative pl-8 md:pl-0 md:pr-10 md:pt-8">
                <span className={`absolute left-0 top-0 h-4 w-4 rounded-full ring-4 ring-night-2 ${dot}`} aria-hidden />
                <div className="text-[13px] text-mist">{layer}</div>
                <div className="mt-1 font-display text-2xl">{name}</div>
                <p className="mt-3 max-w-sm text-[16px] leading-relaxed text-fog">{text}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <footer className="relative z-10 mx-auto max-w-[1400px] px-5 py-16 md:px-10">
        <div className="flex flex-wrap items-center justify-between gap-6">
          <Link href="/twin" className="rounded-full bg-sun px-7 py-3.5 text-[16px] font-medium text-ink hover:bg-sun-deep">See today live</Link>
          <ul className="flex flex-wrap gap-x-5 gap-y-2 text-[13px] text-mist">
            {NAV.map((n) => <li key={n.href}><Link href={n.href} className="hover:text-fog">{n.label}</Link></li>)}
          </ul>
        </div>
        <p className="mt-10 max-w-3xl text-[12px] leading-relaxed text-mist">
          Weather and forecasts are real (NASA POWER, Open-Meteo archives). The village, its bookings and the drive are simulated. Prices and
          factors come from cited publications or are marked as assumptions in constants.yaml. Built for the Schneider Electric Yuva Yodha
          Energy Tech Hackathon 2026, Challenge 1.
        </p>
      </footer>
    </div>
  );
}

function Clock({ t, label, dark = false }: { t: string; label: string; dark?: boolean }) {
  return (
    <div className={`flex items-center gap-3 ${dark ? "text-ink" : "text-sun-ink"}`}>
      <span className="num text-[15px] font-medium">{t}</span>
      <span className={`h-px w-10 ${dark ? "bg-ink/40" : "bg-sun/50"}`} />
      <span className={`text-[14px] ${dark ? "text-ink/80" : "text-mist"}`}>{label}</span>
    </div>
  );
}

function Row({ what, to, dec = 0, prefix = "", unit, base, tone = "text-sun-ink" }: { what: string; to: number; dec?: number; prefix?: string; unit: string; base: string; tone?: string }) {
  return (
    <li className="grid items-baseline gap-x-8 gap-y-1 border-b border-dashed border-fog/25 py-5 md:grid-cols-[220px_minmax(0,1fr)_minmax(0,320px)] md:py-7">
      <div className="text-[14px] text-fog">{what}</div>
      <div className={`num flex items-baseline gap-3 leading-none ${tone}`}>
        <span className="font-display text-[clamp(2.8rem,5.4vw,5rem)] ">{prefix}<span className="count" data-to={to} data-dec={dec}>{to.toLocaleString("en-IN", { maximumFractionDigits: dec, minimumFractionDigits: dec })}</span></span>
        <span className="text-[15px] text-mist">{unit}</span>
      </div>
      <div className="num text-[13px] leading-relaxed text-mist md:text-right">{base}</div>
    </li>
  );
}

const SKY: [number, number[], number[]][] = [
  // [progress, horizon RGBA, paper RGB]: dawn, morning, noon, 13:40 cloud, dusk, evening. Always light, always readable.
  [0.0, [246, 196, 120, 0.5], [251, 245, 231, 1]],
  [0.18, [246, 210, 130, 0.4], [252, 247, 235, 1]],
  [0.36, [250, 224, 150, 0.35], [253, 249, 238, 1]],
  [0.52, [150, 180, 188, 0.4], [243, 241, 231, 1]],
  [0.72, [226, 140, 100, 0.34], [251, 241, 226, 1]],
  [1.0, [185, 207, 143, 0.4], [248, 244, 230, 1]],
];

/** Paint the sky, the sun on its arc and the corner clock for a scroll progress p (0..1). */
/** The story's clock: chapter times between chapters; inside the pinned 13:40 chapter, its own clock. */
function storyMinutes(): number {
  const day = document.querySelector<HTMLElement>(".day");
  const dc = document.querySelector<HTMLElement>(".day-clock");
  if (day && dc) {
    const r = day.getBoundingClientRect();
    if (r.top <= 1 && r.bottom >= window.innerHeight - 1) return Number(dc.textContent || 6) * 60;
  }
  const mark = window.innerHeight * 0.45;
  const anchors: [string, number][] = [[".hero", 330], [".problem", 360], [".beam-wrap", 600], [".day", 600], [".dusk", 1080], ["#proof", 1110], ["#schneider", 1140]];
  const pts = anchors
    .map(([sel, m]) => [document.querySelector<HTMLElement>(sel)?.getBoundingClientRect().top ?? Infinity, m] as [number, number])
    .filter(([y]) => Number.isFinite(y));
  let m = pts[0]?.[1] ?? 360;
  for (let i = 0; i < pts.length; i++) {
    const [y0, m0] = pts[i];
    const next = pts[i + 1];
    if (y0 <= mark) m = m0;
    if (y0 <= mark && next && next[0] > mark && next[1] > m0) m = m0 + ((mark - y0) / (next[0] - y0)) * (next[1] - m0);
  }
  return Math.max(330, Math.min(1140, m));
}

function paintSky(p: number, sky: HTMLDivElement | null, sun: SVGCircleElement | null, hud: HTMLDivElement | null, cum: number[]) {
  const i = Math.max(0, SKY.findIndex(([q]) => q >= p) - 1);
  const [q0, h0, z0] = SKY[i];
  const [q1, h1, z1] = SKY[Math.min(SKY.length - 1, i + 1)];
  const k = q1 > q0 ? (p - q0) / (q1 - q0) : 0;
  const mix = (a: number[], b: number[]) => a.map((v, j) => (j < 3 ? Math.round(v + (b[j] - v) * k) : +(v + (b[j] - v) * k).toFixed(3)));
  const h = mix(h0, h1);
  const z = mix(z0, z1);
  const sx = 0.9 - 0.8 * p;
  if (sky) sky.style.background = `radial-gradient(120% 70% at ${sx * 100}% 100%, rgba(${h.join(",")}) 0%, transparent 70%), rgb(${z.slice(0, 3).join(",")})`;
  if (sun) {
    // the same quadratic arc as the HUD path: M4 24 Q32 -8 60 24
    const u = p;
    sun.setAttribute("cx", String((1 - u) * (1 - u) * 4 + 2 * (1 - u) * u * 32 + u * u * 60));
    sun.setAttribute("cy", String((1 - u) * (1 - u) * 24 + 2 * (1 - u) * u * -8 + u * u * 24));
    sun.style.opacity = p > 0.48 && p < 0.6 ? "0.45" : "1";
  }
  if (hud) {
    const mins = storyMinutes();
    const hh = Math.floor(mins / 60);
    const clock = hud.querySelector('[data-hud="clock"]');
    const kwh = hud.querySelector('[data-hud="kwh"]');
    if (clock) clock.textContent = `${String(hh).padStart(2, "0")}:${String(Math.floor(mins % 60)).padStart(2, "0")}`;
    if (kwh && cum.length > 1) {
      // demo_day hours start 06:30-labelled at index 0; cumulative kWh of real sun to this minute
      const x = Math.max(0, Math.min(cum.length - 1, (mins - 360) / 60));
      const a = Math.floor(x);
      const v = cum[a] + (cum[Math.min(cum.length - 1, a + 1)] - cum[a]) * (x - a);
      kwh.textContent = `${v.toFixed(1)} kWh of real sun so far · 2 Mar 2024`;
    }
  }
}
