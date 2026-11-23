import type { ReactNode } from "react";

export type Source = "real" | "simulated" | "published" | "assumption" | "model";

const SRC: Record<Source, { label: string; cls: string; title: string }> = {
  real: { label: "REAL", cls: "text-leaf border-leaf/40", title: "Measured data (NASA POWER, Open-Meteo)" },
  simulated: { label: "SIMULATED", cls: "text-water border-water/40", title: "Produced by the Prayogshala simulation or a device simulator" },
  published: { label: "PUBLISHED", cls: "text-sun border-sun/40", title: "Taken from a cited publication" },
  assumption: { label: "ASSUMPTION", cls: "text-mist border-mist/40", title: "Modelling assumption; see constants.yaml" },
  model: { label: "MODEL", cls: "text-fog border-fog/40", title: "Model output on real inputs" },
};

export function SourceTag({ kind, className = "" }: { kind: Source; className?: string }) {
  const s = SRC[kind];
  return (
    <span
      title={s.title}
      className={`inline-flex items-center rounded-full border px-2 py-px text-[10px] font-medium tracking-wider num ${s.cls} ${className}`}
    >
      {s.label}
    </span>
  );
}

export function Stat({
  value,
  unit,
  label,
  sub,
  tone = "default",
  source,
  big = false,
}: {
  value: ReactNode;
  unit?: string;
  label: ReactNode;
  sub?: ReactNode;
  tone?: "default" | "sun" | "water" | "leaf" | "se" | "fault";
  source?: Source;
  big?: boolean;
}) {
  const tones = { default: "text-white", sun: "text-sun", water: "text-water", leaf: "text-leaf", se: "text-se", fault: "text-fault" };
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2 text-[12px] text-mist">
        <span>{label}</span>
        {source && <SourceTag kind={source} />}
      </div>
      <div className={`num break-words leading-none ${big ? "text-4xl md:text-6xl" : "text-2xl sm:text-3xl"} ${tones[tone]}`}>
        {value}
        {unit && <span className="ml-1 whitespace-nowrap text-base text-mist">{unit}</span>}
      </div>
      {sub && <div className="text-[12px] text-mist">{sub}</div>}
    </div>
  );
}

export function Panel({ title, right, children, className = "" }: { title?: ReactNode; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`min-w-0 rounded-[10px] border border-soil bg-night-2 ${className}`}>
      {(title || right) && (
        <header className="flex items-center justify-between gap-3 border-b border-soil px-4 py-2.5">
          <h2 className="text-[13px] font-medium text-fog">{title}</h2>
          <div className="flex items-center gap-2">{right}</div>
        </header>
      )}
      <div className="min-w-0 p-4">{children}</div>
    </section>
  );
}

export function Btn({
  children,
  onClick,
  tone = "ghost",
  disabled,
  type = "button",
  className = "",
  ariaLabel,
}: {
  children: ReactNode;
  onClick?: () => void;
  tone?: "ghost" | "sun" | "water" | "fault";
  disabled?: boolean;
  type?: "button" | "submit";
  className?: string;
  ariaLabel?: string;
}) {
  const t = {
    ghost: "border-soil text-fog hover:bg-night-3",
    sun: "border-sun bg-sun text-ink hover:bg-sun-deep",
    water: "border-water bg-water text-ink hover:bg-water-deep hover:text-white",
    fault: "border-fault/60 text-fault hover:bg-fault/10",
  }[tone];
  return (
    <button
      type={type}
      aria-label={ariaLabel}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex min-h-9 items-center justify-center gap-2 rounded-md border px-3 text-[13px] font-medium transition-colors duration-150 disabled:opacity-40 ${t} ${className}`}
    >
      {children}
    </button>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-md border border-dashed border-soil p-6 text-center text-sm text-mist">{children}</div>;
}

export function ErrorNote({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <div role="alert" className="rounded-md border border-fault/50 bg-fault/10 px-3 py-2 text-sm text-fault">
      Cannot reach the SinchaiSlot API ({error}). Start it with <code className="num">make api</code> or{" "}
      <code className="num">docker compose up</code>.
    </div>
  );
}

/** Tabular numeral that rolls only the digits that change (instrument readout). Reduced motion: no roll. */
export function Roll({ value, className = "" }: { value: string; className?: string }) {
  return (
    <span className={`num inline-flex ${className}`}>
      <span className="sr-only">{value}</span>
      {value.split("").map((ch, i) => {
        const d = ch >= "0" && ch <= "9" ? Number(ch) : null;
        if (d === null) return <span key={i} aria-hidden>{ch}</span>;
        return (
          <span key={i} aria-hidden className="relative inline-block h-[1em] overflow-hidden leading-none" style={{ width: "1ch" }}>
            <span className="absolute left-0 top-0 flex flex-col motion-safe:transition-transform motion-safe:duration-500 motion-safe:ease-[cubic-bezier(.2,.7,.1,1)]" style={{ transform: `translateY(-${d}em)` }}>
              {"0123456789".split("").map((n) => <span key={n} className="block h-[1em] leading-none">{n}</span>)}
            </span>
          </span>
        );
      })}
    </span>
  );
}

/** One readout in an instrument strip: label, rolling value, unit; no card around it. */
export function Readout({ label, value, unit, tone = "text-white", sub, source }: { label: ReactNode; value: string; unit?: string; tone?: string; sub?: ReactNode; source?: Source }) {
  return (
    <div className="min-w-0 px-4 py-3 first:pl-0">
      <div className="flex items-center gap-2 text-[11.5px] text-mist">{label}{source && <SourceTag kind={source} />}</div>
      <div className={`mt-1.5 flex items-baseline gap-1 text-[28px] leading-none md:text-[34px] ${tone}`}>
        <Roll value={value} />
        {unit && <span className="whitespace-nowrap text-sm text-mist">{unit}</span>}
      </div>
      {sub && <div className="mt-1.5 text-[11.5px] text-mist">{sub}</div>}
    </div>
  );
}
