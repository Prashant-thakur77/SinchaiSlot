"use client";

import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import Lenis from "lenis";
import Link from "next/link";
import { area, curveMonotoneX, line } from "d3-shape";
import { useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import type { PlotFeature } from "@/components/PlotMosaic";
import { Receipt } from "@/components/Receipt";
import { Mark, NAV } from "@/components/Shell";
import { SourceTag } from "@/components/ui";
import { fmt, getJSON } from "@/lib/api";
import type { LedgerRow, Proof } from "@/lib/types";

gsap.registerPlugin(ScrollTrigger, useGSAP);

const PlotMosaic = dynamic(() => import("@/components/PlotMosaic").then((m) => m.PlotMosaic), { ssr: false });

type Constants = Record<string, { value: number; unit: string; kind: string; source: string | null }>;
type Story = {
  day: string;
  offer: { mai: string; en: string; greet: string } | null;
  callbacks: { name: string; language: string; text: string; at: string }[];
  receipt: LedgerRow | null;
};

export default function Home() {
  const root = useRef<HTMLDivElement>(null);
  const [proof, setProof] = useState<Proof | null>(null);
  const [c, setC] = useState<Constants | null>(null);
  const [story, setStory] = useState<Story | null>(null);
  const [plots, setPlots] = useState<PlotFeature[]>([]);

  useEffect(() => {
    getJSON<Proof>("/api/proof").then(setProof).catch(() => {});
    getJSON<Constants>("/api/constants").then(setC).catch(() => {});
    getJSON<Story>("/api/story").then(setStory).catch(() => {});
    getJSON<{ plots: { features: PlotFeature[] } }>("/api/village").then((v) => setPlots(v.plots.features)).catch(() => {});
  }, []);

  // Smooth scroll (off for reduced motion), driven by GSAP's ticker so ScrollTrigger stays in sync.
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const lenis = new Lenis({ lerp: 0.09 });
    lenis.on("scroll", ScrollTrigger.update);
    const raf = (t: number) => lenis.raf(t * 1000);
    gsap.ticker.add(raf);
    gsap.ticker.lagSmoothing(0);
    return () => {
      gsap.ticker.remove(raf);
      lenis.destroy();
    };
  }, []);

  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        // Hero: the sun rises as you start scrolling; the wordmark settles.
        gsap.from(".wm-l", { yPercent: 110, duration: 1.1, ease: "expo.out", stagger: 0.04 });
        gsap.to(".hero-sun", { yPercent: -60, scale: 1.15, ease: "none", scrollTrigger: { trigger: ".hero", start: "top top", end: "bottom top", scrub: true } });
        gsap.to(".hero-sky", { opacity: 1, ease: "none", scrollTrigger: { trigger: ".hero", start: "top top", end: "bottom top", scrub: true } });
        // 06:00 statement fills word by word.
        gsap.fromTo(".fill-word", { color: "#6b7b72" }, { color: "#eef3ee", stagger: 0.08, ease: "none", scrollTrigger: { trigger: ".problem", start: "top 70%", end: "bottom 60%", scrub: true } });
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
          .fromTo(".curve-band", { opacity: 0 }, { opacity: 1, duration: 0.25 }, 0)
          .fromTo(".curve-p50", { strokeDashoffset: 1 }, { strokeDashoffset: 0, ease: "none", duration: 1 }, 0)
          .fromTo(".day-clock", { innerText: "06" }, { innerText: 18, snap: { innerText: 1 }, ease: "none", duration: 1, onUpdate() { const el = document.querySelector(".day-clock"); if (el) el.textContent = String(el.textContent).padStart(2, "0"); } }, 0)
          .fromTo(".cloud", { xPercent: -120, opacity: 0 }, { xPercent: 40, opacity: 1, duration: 0.3 }, 0.55)
          .to(".cloud", { xPercent: 140, opacity: 0, duration: 0.25 }, 0.85)
          .fromTo(".cloud-note", { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.12 }, 0.62)
          .fromTo(".ring-card", { opacity: 0, y: 40 }, { opacity: 1, y: 0, duration: 0.12 }, 0.7);
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
    },
    { scope: root, dependencies: [proof, story, plots.length], revertOnUpdate: true },
  );

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
    <div ref={root} className="grain overflow-x-clip bg-night text-[#eef3ee]">
      <a href="#story" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-sun focus:px-3 focus:py-1 focus:text-ink">Skip to the story</a>
      <header className="fixed inset-x-0 top-0 z-30 flex items-center justify-between border-b border-white/5 bg-night/75 px-5 py-3 backdrop-blur-md md:px-10">
        <Link href="/" className="flex items-center gap-2 text-white"><Mark /> <span className="font-display text-lg font-semibold">SinchaiSlot</span></Link>
        <nav className="flex items-center gap-5 text-[13px] text-white">
          <a href="#proof" className="hidden hover:underline sm:inline">Proof</a>
          <a href="#schneider" className="hidden hover:underline sm:inline">Schneider inside</a>
          <Link href="/twin" className="rounded-full border border-white px-4 py-1.5 hover:bg-white hover:text-black">Run today live</Link>
        </nav>
      </header>

      {/* HERO */}
      <section className="hero relative flex min-h-[100svh] flex-col justify-end overflow-hidden" aria-label="Introduction">
        <div className="absolute inset-0 bg-[radial-gradient(120%_80%_at_70%_110%,#3a2a0c_0%,#13201a_45%,#0e1512_75%)]" />
        <div className="hero-sky absolute inset-0 bg-[radial-gradient(90%_70%_at_70%_100%,rgba(245,184,61,.35)_0%,rgba(14,21,18,0)_60%)] opacity-40" />
        <div className="hero-sun absolute right-[8%] top-[16%] h-[18vmin] w-[18vmin] rounded-full md:right-[12%] md:top-[58%] md:h-[22vmin] md:w-[22vmin] bg-sun shadow-[0_0_120px_40px_rgba(245,184,61,.35)]" aria-hidden />
        <div className="relative z-10 mx-auto w-full max-w-[1400px] px-5 pb-6 md:px-10">
          <p className="max-w-3xl font-display text-[clamp(1.7rem,3.6vw,3.4rem)] font-semibold leading-[1.05] tracking-tight text-[#eef3ee]">
            Every shared solar pump in Bihar is a 5&nbsp;kW power plant that sleeps most of the day.
          </p>
          <p className="mt-5 max-w-2xl text-[15px] leading-relaxed text-mist">
            SinchaiSlot wakes it up: water first for the farmers who book it, then the flour mill, the chaff cutter and battery packs with the
            sun that is left, all inside the village&apos;s groundwater budget. Planned on tomorrow&apos;s forecast, run and metered by a
            Schneider Altivar Solar drive, receipted for every litre.
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            <Link href="/twin" className="rounded-full bg-sun px-6 py-3 text-[15px] font-semibold text-ink hover:bg-sun-deep">Run 2 March live</Link>
            <a href="#story" className="rounded-full border border-fog/40 px-6 py-3 text-[15px] hover:bg-white/5">Follow one day ↓</a>
          </div>
        </div>
        <h1 className="wm relative z-10 select-none overflow-hidden px-3 pb-2 font-display font-extrabold leading-[0.8] tracking-[-0.02em] text-sun" aria-label="SinchaiSlot">
          <span className="flex justify-between text-[clamp(3.2rem,13.5vw,15rem)]" aria-hidden>
            {"SINCHAISLOT".split("").map((ch, i) => <span key={i} className="wm-l inline-block">{ch}</span>)}
          </span>
        </h1>
      </section>

      {/* 06:00 PROBLEM */}
      <section id="story" className="problem relative mx-auto max-w-[1400px] px-5 py-[18vh] md:px-10" aria-labelledby="t-problem">
        <Clock t="06:00" label="Dawn, Samastipur" />
        <h2 id="t-problem" className="mt-8 max-w-5xl font-display text-[clamp(2.2rem,5.6vw,5.5rem)] font-semibold leading-[1.02] tracking-tight">
          {`Solar pumps put about ${ceew ? Math.round(ceew.value * 100) : "…"}% of their sunshine to work. Next door, a tenant farmer pays a diesel seller ₹${dieselRate?.value ?? "…"} an hour for the same water.`
            .split(" ")
            .map((w, i) => <span key={i} className="fill-word">{w} </span>)}
        </h2>
        <div className="mt-10 grid max-w-4xl gap-6 text-[14px] text-mist sm:grid-cols-3">
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
      <section className="beam-wrap relative min-h-[110vh]" aria-labelledby="t-book">
        <div className="beam absolute inset-0 bg-sun" style={{ clipPath: "polygon(0% 0%, 100% 0%, 100% 100%, 0% 100%)" }} aria-hidden />
        <div className="relative mx-auto grid max-w-[1400px] items-center gap-10 px-5 py-[16vh] text-ink md:grid-cols-[1.1fr_0.9fr] md:px-10">
          <div>
            <Clock t="10:00" label="Ramesh gives a missed call" dark />
            <h2 id="t-book" className="mt-8 font-display text-[clamp(2rem,5vw,4.6rem)] font-semibold leading-[1.02] tracking-tight">
              The call is free. Saathi calls back in Maithili, already knowing what his wheat needs.
            </h2>
            <p className="mt-6 max-w-xl text-[16px] leading-relaxed">
              The booking is sized to the crop by the FAO-56 water balance on today&apos;s weather, so nobody books more than the field can use.
              Saathi reads the offer back and books only after he says yes. Price per cubic metre, under diesel.
            </p>
          </div>
          <div className="phone-card mx-auto w-full max-w-sm rounded-[28px] bg-ink p-5 text-paper shadow-[0_30px_60px_-20px_rgba(19,32,26,.6)]">
            <div className="flex items-center justify-between text-[12px] opacity-70"><span>Saathi · callback</span><span className="num">{story?.day ?? ""}</span></div>
            <p className="deva mt-4 text-[17px] leading-relaxed" lang="mai">{story?.offer ? `${story.offer.greet} ${story.offer.mai}` : "…"}</p>
            <p className="mt-4 border-t border-paper/15 pt-3 text-[13px] leading-relaxed opacity-75">{story?.offer?.en}</p>
            <div className="mt-4 flex gap-2 text-[13px]">
              <span className="rounded-full bg-sun px-3 py-1 font-semibold text-ink">1 · हँ</span>
              <span className="rounded-full border border-paper/30 px-3 py-1">2 · नै</span>
            </div>
            <p className="mt-3 text-[11px] opacity-60">Live from the planner on the demo day. Voice simulated as text.</p>
          </div>
        </div>
      </section>

      {/* 13:40 THE CLOUD (signature) */}
      <section className="day relative flex h-[100svh] min-h-[600px] flex-col justify-center overflow-hidden bg-night py-10" aria-labelledby="t-cloud">
        {plots.length > 0 && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center opacity-[0.07]" aria-hidden>
            <div className="w-[120vmin]"><PlotMosaic features={plots} /></div>
          </div>
        )}
        <div className="cloud pointer-events-none absolute top-[10%] h-[60vh] w-[70vw] rounded-full bg-[radial-gradient(closest-side,rgba(4,8,7,.75),rgba(4,8,7,0))]" aria-hidden />
        <div className="relative mx-auto w-full max-w-[1400px] px-5 md:px-10">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <Clock t="13:40" label="A cloud band crosses the afternoon" />
              <h2 id="t-cloud" className="mt-4 max-w-3xl font-display text-[clamp(1.5rem,3vw,2.8rem)] font-semibold leading-[1.05] tracking-tight">
                The forecast said sun. The sky said otherwise. The plan moves before the water stops.
              </h2>
            </div>
            <div className="text-left md:text-right">
              <div className="num text-[clamp(2.6rem,6vw,5.5rem)] leading-none text-sun"><span className="day-clock">18</span>:00</div>
              <div className="text-[12px] text-mist">{day?.date} · real sun, held-out day <SourceTag kind="real" /></div>
            </div>
          </div>
          {chart && (
            <div className="relative mt-6">
              <svg viewBox={`0 0 ${chart.W} ${chart.H}`} preserveAspectRatio="none" className="h-[34vh] w-full overflow-visible" role="img" aria-label="Solar power on the demo day: forecast band, forecast median and actual">
                <path className="curve-band" d={chart.band} fill="var(--sun)" opacity="0.22" />
                <path className="curve-p50" d={chart.p50} pathLength={1} strokeDasharray="1" fill="none" stroke="var(--sun-deep)" strokeWidth="3" strokeOpacity="0.8" vectorEffect="non-scaling-stroke" />
                <path className="curve-actual" d={chart.actual} pathLength={1} strokeDasharray="1" fill="none" stroke="#fff" strokeWidth="4" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
              </svg>
              <div className="cloud-note pointer-events-none absolute flex items-center gap-2" style={{ left: `${(chart.cloudX / chart.W) * 100}%`, top: `${(chart.cloudY / chart.H) * 100}%`, transform: "translate(-7px, -7px)" }}>
                <span className="h-3.5 w-3.5 rounded-full bg-water ring-4 ring-water/25" />
                <span className="whitespace-nowrap rounded bg-night/80 px-2 py-0.5 text-[13px] text-water">actual sun below the P10 forecast</span>
              </div>
              <div className="mt-2 flex flex-wrap gap-4 text-[12px] text-mist">
                <span><span className="mr-1.5 inline-block h-2 w-5 bg-sun/30 align-middle" />P10 to P90 forecast</span>
                <span><span className="mr-1.5 inline-block w-5 border-t-2 border-sun-deep align-middle" />P50</span>
                <span><span className="mr-1.5 inline-block w-5 border-t-[3px] border-white align-middle" />actual sun</span>
              </div>
            </div>
          )}
          <div className="mt-5 grid gap-5 md:grid-cols-[1fr_minmax(0,380px)]">
            <p className="max-w-2xl text-[14px] leading-relaxed text-mist">
              Surya Planner re-solves the day from now with the nowcast. It never moves the slot that is running or the next one. Water still
              comes first; the mill waits for the sun that is left. Every moved farmer gets a call in their own language, and if less water
              fits today, Saathi says so and puts them first tomorrow.
            </p>
            <div className="ring-card rounded-2xl border border-water/40 bg-night-2 p-4">
              {story?.callbacks?.length ? (
                <>
                  <div className="num text-[12px] text-water">📞 {story.callbacks[story.callbacks.length - 1].at} · {story.callbacks[story.callbacks.length - 1].name}</div>
                  <p className="deva mt-2 text-[15px]" lang="mai">{story.callbacks[story.callbacks.length - 1].text}</p>
                </>
              ) : (
                <>
                  <div className="text-[12px] text-water">📞 Plan-change calls</div>
                  <p className="mt-2 text-[14px] text-fog">Run the day in the Village Twin to hear who gets called, and what they are told.</p>
                  <Link href="/twin" className="mt-3 inline-block text-[13px] text-sun underline">Open the live day</Link>
                </>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* 18:00 DUSK RECEIPT */}
      <section className="dusk relative bg-[linear-gradient(180deg,#0e1512_0%,#1a1510_100%)] py-[16vh]" aria-labelledby="t-receipt">
        <div className="mx-auto grid max-w-[1400px] items-center gap-12 px-5 md:grid-cols-2 md:px-10">
          <div>
            <Clock t="18:00" label="The pump stops; the books close" />
            <h2 id="t-receipt" className="mt-8 font-display text-[clamp(2rem,4.6vw,4.2rem)] font-semibold leading-[1.03] tracking-tight">
              Every booking leaves a receipt a funder can pay against.
            </h2>
            <p className="mt-6 max-w-xl text-[15px] leading-relaxed text-mist">
              Litres, kilowatt-hours, diesel and CO₂ avoided, read from the drive and chained by hash to the receipt before it. Edit one and the
              chain breaks. Receipts become CSR claims, a lender&apos;s credit file, and, with a rule change, the state diesel subsidy.
            </p>
          </div>
          <div className="receipt-slot mx-auto w-full max-w-sm">{story?.receipt && <Receipt r={story.receipt} />}</div>
        </div>
      </section>

      {/* PROOF */}
      <section id="proof" className="mx-auto max-w-[1400px] px-5 py-[14vh] md:px-10" aria-labelledby="t-proof">
        <div className="flex flex-wrap items-baseline justify-between gap-4">
          <h2 id="t-proof" className="font-display text-[clamp(2rem,4.6vw,4.2rem)] font-semibold tracking-tight">The proof</h2>
          <p className="max-w-xl text-[13px] text-mist">
            {proof ? `${proof.setup.runs_per_policy} simulated years per policy on real NASA POWER weather (${proof.setup.years.join(", ")}, held out), real archived forecasts, ${proof.setup.seeds} synthetic villages. Bands are P10 to P90.` : "Loading reports/proof.json…"}{" "}
            <SourceTag kind="simulated" />
          </p>
        </div>
        {h && pol && (
          <div className="mt-10 grid gap-x-10 gap-y-12 sm:grid-cols-2 lg:grid-cols-3">
            <Big to={h.utilisation_D_kwh_per_kwp} unit="kWh per kWp per year of sun put to work" sub={`Chakhaji-style first-come baseline: ${fmt.n(h.utilisation_B_kwh_per_kwp)}`} />
            <Big to={h.utilisation_gain_vs_B * 100} dec={0} prefix="+" unit="% more solar used than the baseline" sub={`P10 ${fmt.signedPct(proof!.gains.utilisation_D_vs_B.p10)} to P90 ${fmt.signedPct(proof!.gains.utilisation_D_vs_B.p90)}`} />
            <Big to={h.farmer_rs_per_m3_D} dec={2} prefix="₹" unit="per m³ of solar water for the farmer" sub={`Baseline ₹${h.farmer_rs_per_m3_B.toFixed(2)} · diesel ₹${h.diesel_rs_per_m3.toFixed(2)}`} />
            <Big to={h.tenant_share_D * 100} dec={0} unit="% of tenant water need met by solar" sub={`Baseline ${fmt.pct(h.tenant_share_B)} · Gini of access ${h.gini_D.toFixed(2)} vs ${h.gini_B.toFixed(2)}`} />
            <Big to={h.diesel_l_avoided_D} unit="litres of diesel avoided per pump-year" sub={`${fmt.n(h.co2_kg_avoided_D)} kg CO₂ · factor 2.6444 kg/L, published`} />
            <Big to={h.forecast_skill_vs_persistence * 100} dec={0} unit="% better solar forecast than yesterday's sun" sub={`Held-out ${proof!.forecast.test_years.join("-")} · ${fmt.pct(h.forecast_skill_vs_climatology)} better than climatology`} />
          </div>
        )}
        {proof?.negative_results?.explanation && (
          <div className="mt-14 max-w-3xl border-l-2 border-sun/60 pl-5">
            <div className="text-[13px] text-sun">What the planner does not add</div>
            <p className="mt-2 font-serif text-[19px] leading-relaxed text-fog">{proof.negative_results.explanation}</p>
          </div>
        )}
        <Link href="/lab" className="mt-10 inline-block rounded-full border border-fog/40 px-5 py-2.5 text-[14px] hover:bg-white/5">Every number, every band, every ablation →</Link>
      </section>

      {/* SCHNEIDER */}
      <section id="schneider" className="border-t border-soil bg-night-2" aria-labelledby="t-se">
        <div className="mx-auto max-w-[1400px] px-5 py-[12vh] md:px-10">
          <h2 id="t-se" className="font-display text-[clamp(1.8rem,4vw,3.4rem)] font-semibold tracking-tight">
            Remove the <span className="text-se">Altivar Solar</span> drive and nothing works.
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
                <p className="mt-3 max-w-sm text-[14px] leading-relaxed text-mist">{text}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <footer className="mx-auto max-w-[1400px] px-5 py-16 md:px-10">
        <div className="flex flex-wrap items-center justify-between gap-6">
          <Link href="/twin" className="rounded-full bg-sun px-7 py-3.5 text-[16px] font-semibold text-ink hover:bg-sun-deep">Run today live</Link>
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
    <div className={`flex items-center gap-3 ${dark ? "text-ink" : "text-sun"}`}>
      <span className="num text-[15px] font-medium">{t}</span>
      <span className={`h-px w-10 ${dark ? "bg-ink/40" : "bg-sun/50"}`} />
      <span className={`text-[14px] ${dark ? "text-ink/80" : "text-mist"}`}>{label}</span>
    </div>
  );
}

function Big({ to, dec = 0, prefix = "", unit, sub }: { to: number; dec?: number; prefix?: string; unit: string; sub: string }) {
  return (
    <div>
      <div className="num text-[clamp(3rem,6vw,5.5rem)] leading-none text-sun">
        {prefix}
        <span className="count" data-to={to} data-dec={dec}>{to.toLocaleString("en-IN", { maximumFractionDigits: dec, minimumFractionDigits: dec })}</span>
      </div>
      <div className="mt-3 text-[15px] text-fog">{unit}</div>
      <div className="num mt-1 text-[12px] text-mist">{sub}</div>
    </div>
  );
}
