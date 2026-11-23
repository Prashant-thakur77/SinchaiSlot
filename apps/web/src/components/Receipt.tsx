import type { LedgerRow } from "@/lib/types";

/** Rasid: a verified receipt printed on ledger paper. */
export function Receipt({ r, fresh = false, stamp = "verified" }: { r: LedgerRow; fresh?: boolean; stamp?: "verified" | "pending" | "checking" }) {
  const water = r.kind === "water";
  return (
    <article
      className={`paper perforated relative rounded-b-md px-4 pb-4 pt-5 shadow-[0_10px_30px_-12px_rgba(110,80,30,.22)] ${fresh ? "print-in" : ""}`}
      aria-label={`Receipt ${r.receipt_id}`}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-display text-[22px]">Rasid</span>
        <span className="num text-[11px] opacity-70">{r.receipt_id}</span>
      </div>
      <div className="num mt-1 text-[11px] opacity-70">
        {r.start.replace("T", " ")} → {r.end.slice(11)} · pump {r.pump_id}
        {r.plot_id ? ` · plot ${r.plot_id}` : ""}
      </div>
      <dl className="num mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-[13px]">
        {water ? (
          <>
            <dt className="opacity-70">Water</dt>
            <dd className="text-right font-medium">{r.m3.toFixed(1)} m³</dd>
          </>
        ) : (
          <>
            <dt className="opacity-70">{r.kind === "mill" ? "Flour mill" : r.kind === "chaff" ? "Chaff cutter" : "Battery packs"}</dt>
            <dd className="text-right font-medium">solar service</dd>
          </>
        )}
        <dt className="opacity-70">Solar energy</dt>
        <dd className="text-right">{r.kwh.toFixed(2)} kWh</dd>
        {water && (
          <>
            <dt className="opacity-70">Diesel avoided</dt>
            <dd className="text-right">{r.diesel_l_avoided.toFixed(2)} L</dd>
            <dt className="opacity-70">CO₂ avoided</dt>
            <dd className="text-right">{r.co2_kg_avoided.toFixed(2)} kg</dd>
          </>
        )}
        <dt className="opacity-70">Amount</dt>
        <dd className="text-right">₹{r.amount_rs.toFixed(0)}</dd>
      </dl>
      <div className="mt-3 flex items-center justify-between border-t border-dashed border-ink/25 pt-2">
        <span className="num truncate text-[10px] opacity-60" title={r.hash}>
          #{r.hash.slice(0, 16)}… ← {r.prev_hash.slice(0, 6)}
        </span>
        {stamp === "verified" ? (
          <span className="stamp-in ml-2 shrink-0 rotate-[-4deg] rounded border-2 border-[#1d8a37] px-1.5 text-[10px] font-semibold tracking-wider text-[#1d8a37]">VERIFIED</span>
        ) : (
          <span className={`ml-2 shrink-0 rounded border border-dashed border-ink/30 px-1.5 text-[10px] tracking-wider text-ink/50 ${stamp === "checking" ? "animate-pulse" : ""}`}>{stamp === "checking" ? "CHECKING" : "HASH"}</span>
        )}
      </div>
      <div className="mt-1 text-[10px] opacity-60">{r.method === "drive-estimate" ? "Water metered from Altivar drive telemetry" : r.method}</div>
    </article>
  );
}
