import type { ReactNode } from "react";

/**
 * Line art in the village's own tradition: Mithila wall painting, which is what Samastipur's walls carry.
 * Its grammar, kept throughout: a double ink contour, flat natural pigments, fine hatching inside shapes,
 * round eyes, and no empty ground inside a figure. Everything here is drawn in code; nothing is an image.
 */

const INK = "var(--ink)";
const PAPER = "var(--night)";

/** A shape with the double contour: thick ink line with a thin paper line running inside it. */
function D({ d, fill = "none", w = 5, hatch }: { d: string; fill?: string; w?: number; hatch?: string }) {
  return (
    <g strokeLinejoin="round" strokeLinecap="round">
      <path d={d} fill={fill} stroke={INK} strokeWidth={w} />
      {hatch && <path d={d} fill={`url(#${hatch})`} />}
      <path d={d} fill="none" stroke={PAPER} strokeWidth={w * 0.4} />
    </g>
  );
}

/** Same double contour for a circle. */
function C({ x = 0, y = 0, r, fill = "none", w = 5 }: { x?: number; y?: number; r: number; fill?: string; w?: number }) {
  return (
    <g>
      <circle cx={x} cy={y} r={r} fill={fill} stroke={INK} strokeWidth={w} />
      <circle cx={x} cy={y} r={r} fill="none" stroke={PAPER} strokeWidth={w * 0.4} />
    </g>
  );
}

export function ArtDefs() {
  const h = (id: string, color: string, rot: number, gap = 6, o = 0.5) => (
    <pattern id={id} width={gap} height={gap} patternUnits="userSpaceOnUse" patternTransform={`rotate(${rot})`}>
      <line x1="0" y1="0" x2="0" y2={gap} stroke={color} strokeWidth="1.3" opacity={o} />
    </pattern>
  );
  return (
    <defs>
      {h("h-ink", "var(--ink)", 35, 6, 0.4)}
      {h("h-ink2", "var(--ink)", -40, 7, 0.32)}
      {h("h-v", "var(--ink)", 0, 8, 0.3)}
      <pattern id="h-scale" width="14" height="10" patternUnits="userSpaceOnUse">
        <path d="M0 0a7 7 0 0 0 14 0M-7 5a7 7 0 0 0 14 0M7 5a7 7 0 0 0 14 0" fill="none" stroke="var(--ink)" strokeWidth="1.1" opacity=".55" />
      </pattern>
      <pattern id="h-wave" width="48" height="20" patternUnits="userSpaceOnUse">
        <path d="M0 10q12 -9 24 0t24 0" fill="none" stroke="var(--ink)" strokeWidth="1.4" opacity=".38" />
      </pattern>
    </defs>
  );
}

const ring = (n: number) => Array.from({ length: n }, (_, i) => (i * 360) / n);

export function SunFace({ r = 60, spin = true }: { r?: number; spin?: boolean }) {
  const s = r / 60;
  return (
    <g transform={`scale(${s})`}>
      <g className={spin ? "art-spin" : undefined}>
        {ring(20).map((a, i) => (
          <g key={a} transform={`rotate(${a})`}>
            <path d={i % 2 ? "M-8 -66 Q0 -104 8 -66Z" : "M-9 -66 L0 -116 L9 -66Z"} fill={i % 2 ? "var(--terra)" : "var(--sun)"} stroke={INK} strokeWidth="2.6" strokeLinejoin="round" />
          </g>
        ))}
      </g>
      <C r={64} fill="var(--terra)" w={4} />
      {ring(28).map((a) => <circle key={a} cx="0" cy="-55" r="3" fill={PAPER} transform={`rotate(${a})`} />)}
      <C r={47} fill="var(--sun)" w={4} />
      {/* face */}
      <path d="M-29 -10q11 -11 22 0q-11 10 -22 0zM7 -10q11 -11 22 0q-11 10 -22 0z" fill={PAPER} stroke={INK} strokeWidth="2.2" />
      <circle cx="-18" cy="-10" r="4.4" fill={INK} /><circle cx="18" cy="-10" r="4.4" fill={INK} />
      <path d="M-31 -21q13 -10 25 -1M31 -21q-13 -10 -25 -1M-2 -12q-7 17 -1 19q4 1 6 -2" fill="none" stroke={INK} strokeWidth="2.4" strokeLinecap="round" />
      <path d="M-13 18q13 12 26 0q-13 -5 -26 0z" fill="var(--terra)" stroke={INK} strokeWidth="2" />
      <circle cx="-29" cy="9" r="5" fill="var(--terra)" opacity=".55" /><circle cx="29" cy="9" r="5" fill="var(--terra)" opacity=".55" />
      <path d="M0 -34v8" stroke="var(--terra)" strokeWidth="4" strokeLinecap="round" />
    </g>
  );
}

export function Fish({ fill = "var(--terra)" }: { fill?: string }) {
  return (
    <g>
      <D d="M54 0 L86 -24 Q78 0 86 24 Z" fill="var(--sun)" hatch="h-ink" w={4} />
      <D d="M-60 0 Q-20 -36 30 -22 Q50 -12 58 0 Q50 12 30 22 Q-20 36 -60 0 Z" fill={fill} hatch="h-scale" w={4.5} />
      <D d="M-10 -28 Q8 -48 28 -22" fill="var(--leaf)" w={3.4} />
      <path d="M-28 -20q10 20 0 40" fill="none" stroke={INK} strokeWidth="2.4" />
      <circle cx="-40" cy="-5" r="7" fill={PAPER} stroke={INK} strokeWidth="2.4" /><circle cx="-41" cy="-5" r="2.8" fill={INK} />
    </g>
  );
}

export function Lotus({ fill = "var(--rose)" }: { fill?: string }) {
  return (
    <g>
      <D d="M0 8 Q-58 6 -62 -26 Q-30 -26 0 8Z" fill={fill} hatch="h-ink2" w={3.6} />
      <D d="M0 8 Q58 6 62 -26 Q30 -26 0 8Z" fill={fill} hatch="h-ink2" w={3.6} />
      <D d="M0 8 Q-40 -18 -32 -52 Q-6 -36 0 8Z" fill={fill} w={3.6} />
      <D d="M0 8 Q40 -18 32 -52 Q6 -36 0 8Z" fill={fill} w={3.6} />
      <D d="M0 8 Q-22 -32 0 -66 Q22 -32 0 8Z" fill={fill} hatch="h-v" w={3.6} />
    </g>
  );
}

export function Parrot() {
  return (
    <g>
      <D d="M14 26 Q42 52 70 88 Q34 82 2 44Z" fill="var(--water)" hatch="h-ink" w={4} />
      <D d="M-34 -18 Q-40 -54 -8 -58 Q24 -56 28 -18 Q36 22 14 40 Q-14 50 -26 22 Q-34 6 -34 -18Z" fill="var(--leaf)" w={4.5} />
      <D d="M2 -14 Q34 -8 24 36 Q-6 36 -8 8 Q-8 -8 2 -14Z" fill="var(--leaf)" hatch="h-scale" w={3.4} />
      <path d="M-34 -36 Q-58 -34 -50 -14 Q-44 -20 -33 -20Z" fill="var(--terra)" stroke={INK} strokeWidth="3" strokeLinejoin="round" />
      <path d="M-32 -14q16 10 32 -2" fill="none" stroke="var(--terra)" strokeWidth="5" strokeLinecap="round" />
      <circle cx="-17" cy="-37" r="8" fill={PAPER} stroke={INK} strokeWidth="2.6" /><circle cx="-18" cy="-37" r="3.2" fill={INK} />
    </g>
  );
}

/** A leafy tree: trunk with a symmetric crown of hatched leaves, the way wall painters fill it. */
export function Tree({ crown = "var(--leaf)", fruit = "var(--terra)" }: { crown?: string; fruit?: string }) {
  return (
    <g>
      <D d="M-9 90 Q-4 30 -6 0 L6 0 Q4 30 9 90Z" fill="var(--terra)" hatch="h-v" w={4} />
      {[0, 24, -24, 50, -50, 78, -78].map((a, i) => (
        <g key={a} transform={`rotate(${a}) `}>
          <D d="M0 8 Q-24 -42 0 -92 Q24 -42 0 8Z" fill={crown} hatch={i % 2 ? "h-ink" : "h-ink2"} w={3.6} />
          <path d="M0 0V-82" stroke={INK} strokeWidth="1.6" />
        </g>
      ))}
      {[-64, -37, -12, 12, 37, 64].map((a) => <circle key={a} cx="0" cy="-70" r="6.5" fill={fruit} stroke={INK} strokeWidth="2" transform={`rotate(${a})`} />)}
    </g>
  );
}

export function Wheat() {
  return (
    <g>
      <path d="M0 60 Q3 10 0 -30" fill="none" stroke="var(--leaf-deep)" strokeWidth="3.4" strokeLinecap="round" />
      {[0, 1, 2, 3].map((i) => (
        <g key={i} transform={`translate(0 ${-28 + i * 13})`} fill="var(--sun)" stroke={INK} strokeWidth="1.8">
          <path d="M0 8 Q-15 4 -12 -13 Q0 -6 0 8Z" /><path d="M0 8 Q15 4 12 -13 Q0 -6 0 8Z" />
        </g>
      ))}
      <path d="M0 -24 Q-7 -38 0 -50 Q7 -38 0 -24Z" fill="var(--sun)" stroke={INK} strokeWidth="1.8" />
    </g>
  );
}

export function Panel3() {
  return (
    <g>
      <path d="M0 10V66M-26 66H26" stroke={INK} strokeWidth="6" strokeLinecap="round" />
      <D d="M-78 18 L-52 -44 L86 -44 L60 18Z" fill="var(--water)" w={5} />
      <path d="M-65 -13H73M-32 -44L-58 18M-4 -44L-27 18M25 -44L2 18M55 -44L31 18" stroke={INK} strokeWidth="2" />
      <path d="M-46 -38l-8 18M-18 -38l-8 18M10 -38l-8 18M40 -38l-8 18" stroke={PAPER} strokeWidth="2.4" opacity=".8" />
    </g>
  );
}

/** The pump head with its arc of water. */
export function PumpHead({ flow = true }: { flow?: boolean }) {
  return (
    <g>
      <D d="M-26 60 L-26 -12 Q-26 -30 -8 -30 L20 -30 L20 -8 L-2 -8 L-2 60Z" fill="var(--terra)" hatch="h-v" w={4.5} />
      <D d="M18 -36 L34 -36 L34 -2 L18 -2Z" fill="var(--sun)" w={4} />
      {[0, 1, 2].map((i) => (
        <path key={i} d={`M36 ${-28 + i * 8} Q${88 - i * 12} ${-26 + i * 10} ${96 - i * 12} 60`} fill="none" stroke={i === 1 ? "var(--water)" : "var(--water-deep)"} strokeWidth="4" strokeLinecap="round"
          className={flow ? "flow-line" : undefined} style={{ ["--flow-dur" as string]: `${1.6 + i * 0.3}s` }} />
      ))}
    </g>
  );
}

function Cloud() {
  return (
    <g>
      <D d="M-70 22 Q-92 -4 -60 -18 Q-54 -52 -18 -40 Q8 -64 34 -36 Q74 -40 74 -8 Q92 18 62 22Z" fill="var(--mistfill)" hatch="h-wave" w={4.5} />
      {[-44, -16, 12, 40].map((x) => <path key={x} d={`M${x} 34l-6 20`} stroke="var(--water-deep)" strokeWidth="4" strokeLinecap="round" />)}
    </g>
  );
}

function Pot() {
  return (
    <g>
      <D d="M-22 -36 Q-52 -4 -40 30 Q-24 54 0 54 Q24 54 40 30 Q52 -4 22 -36Z" fill="var(--terra)" w={4.5} />
      <D d="M-30 -48 L30 -48 L22 -34 L-22 -34Z" fill="var(--sun)" w={4} />
      <path d="M-44 2q11 -14 22 0t22 0t22 0t22 0M-40 22q10 12 20 0t20 0t20 0t20 0" fill="none" stroke={PAPER} strokeWidth="3.4" />
      {[-24, -8, 8, 24].map((x) => <circle key={x} cx={x} cy="12" r="3.6" fill="var(--sun)" />)}
    </g>
  );
}

function Wheel() {
  return (
    <g>
      <C r={58} fill="var(--sun)" />
      <C r={42} fill={PAPER} w={4} />
      {ring(8).map((a) => <path key={a} d="M0 -8 Q-12 -26 0 -42 Q12 -26 0 -8Z" fill="var(--terra)" stroke={INK} strokeWidth="2.4" transform={`rotate(${a})`} />)}
      <C r={9} fill="var(--leaf)" w={3} />
      {ring(16).map((a) => <circle key={a} cx="0" cy="-50" r="3" fill={INK} transform={`rotate(${a})`} />)}
    </g>
  );
}

function Vine() {
  return (
    <g>
      <path d="M-74 30 Q-38 -50 0 0 T74 -30" fill="none" stroke={INK} strokeWidth="5" strokeLinecap="round" />
      {[[-56, 0, -60], [-30, -24, 20], [-4, -4, 120], [26, 24, 170], [52, 4, 20]].map(([x, y, a]) => (
        <g key={x} transform={`translate(${x} ${y}) rotate(${a})`}><D d="M0 0 Q-15 -18 0 -38 Q15 -18 0 0Z" fill="var(--leaf)" hatch="h-ink" w={3} /></g>
      ))}
      <C x={-74} y={32} r={9} fill="var(--terra)" w={3} /><C x={76} y={-32} r={9} fill="var(--sun)" w={3} />
    </g>
  );
}

const MOTIF: Record<string, ReactNode> = {
  sun: <SunFace r={42} spin={false} />,
  cloud: <Cloud />,
  parrot: <g transform="translate(-4 -8) scale(.92)"><Parrot /></g>,
  lotus: <g transform="translate(0 26)"><Lotus /></g>,
  wheel: <Wheel />,
  fish: <g transform="translate(-10 0)"><Fish /></g>,
  tree: <g transform="translate(0 14) scale(.78)"><Tree /></g>,
  vine: <Vine />,
  pot: <Pot />,
  pump: <g transform="translate(-24 -8)"><PumpHead flow={false} /></g>,
};

/** One painted motif, used once per page beside its title. */
export function Motif({ name, size = 64 }: { name: string; size?: number }) {
  return (
    <svg viewBox="-90 -90 180 180" width={size} height={size} aria-hidden className="shrink-0 overflow-visible">
      <ArtDefs />
      {MOTIF[name]}
    </svg>
  );
}

/** A painted border band: the leaf-and-bud strip that frames every wall panel. */
export function Border({ className = "", id = "bd" }: { className?: string; id?: string }) {
  return (
    <svg className={`block h-5 w-full ${className}`} aria-hidden>
      <defs>
        <pattern id={id} width="44" height="20" patternUnits="userSpaceOnUse">
          <path d="M0 2.5H44M0 17.5H44" stroke="var(--ink)" strokeWidth="1.2" />
          <path d="M4 10 Q13 2 22 10 Q13 18 4 10Z" fill="var(--leaf)" stroke="var(--ink)" strokeWidth="1.1" />
          <path d="M4 10H22" stroke="var(--ink)" strokeWidth=".8" />
          <path d="M33 4.5L39 10L33 15.5L27 10Z" fill="var(--terra)" stroke="var(--ink)" strokeWidth="1.1" />
          <circle cx="33" cy="10" r="1.8" fill="var(--night)" />
        </pattern>
      </defs>
      <rect width="100%" height="20" fill={`url(#${id})`} />
    </svg>
  );
}

/** The opening wall: sun, panels, pump, wheat, pond. Ambient motion only; still under reduced motion. */
export function VillageScene({ className = "" }: { className?: string }) {
  const wheat = [...Array(17)].map((_, i) => [612 + i * 30, 452 + ((i * 37) % 22), 0.82 + ((i * 13) % 5) / 22] as const);
  return (
    <svg viewBox="0 0 1440 620" preserveAspectRatio="xMidYMax slice" className={`overflow-visible ${className}`} role="img" aria-label="A Mithila-style painting: the sun above a solar panel, a pump pouring water, a wheat field and a lotus pond with fish">
      <ArtDefs />
      <g className="art-sunpos"><g className="scene-sun"><SunFace r={74} /></g></g>
      {/* ground bands */}
      <D d="M-20 432 Q240 372 520 420 T1010 408 T1460 396 V640 H-20Z" fill="var(--field)" hatch="h-ink2" w={5} />
      <D d="M-20 500 Q260 462 540 496 T1080 492 T1460 480 V640 H-20Z" fill="var(--wheatfield)" hatch="h-v" w={5} />
      {/* trees and birds */}
      <g className="art-lefttrees"><g transform="translate(120 372) scale(1.15)"><Tree /></g>
      <g transform="translate(330 388) scale(.82)"><Tree crown="var(--leaf-deep)" fruit="var(--sun)" /></g></g>
      <g transform="translate(1362 352) scale(1.05)"><Tree fruit="var(--sun)" /></g>
      <g transform="translate(800 318) scale(.6)" className="art-parrot"><g className="art-bob"><Parrot /></g></g>
      {/* wheat */}
      {wheat.map(([x, y, s], i) => <g key={i} transform={`translate(${x} ${y}) scale(${s})`}><g className="art-sway" style={{ animationDelay: `${-i * 0.37}s` }}><Wheat /></g></g>)}
      {/* panels, pump */}
      <g transform="translate(1222 396) scale(1.15)"><Panel3 /></g>
      <g transform="translate(470 440) scale(1.1)"><PumpHead /></g>
      {/* pond */}
      <D d="M180 600 Q200 520 470 516 Q760 506 900 536 Q1010 556 1010 640 H180Z" fill="var(--water)" hatch="h-wave" w={6} />
      <g transform="translate(395 586) scale(.72)"><g className="art-swim"><Fish /></g></g>
      <g transform="translate(720 596) scale(-.62 .62)"><g className="art-swim" style={{ animationDelay: "-4s" }}><Fish fill="var(--sun)" /></g></g>
      <g transform="translate(565 572) scale(.62)" className="art-bob"><Lotus /></g>
      <g transform="translate(880 590) scale(.5)"><Lotus fill="var(--sun)" /></g>
    </svg>
  );
}
