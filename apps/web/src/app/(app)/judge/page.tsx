"use client";

import Link from "next/link";
import { Shell } from "@/components/Shell";
import { ErrorNote } from "@/components/ui";
import { fmt, useApi } from "@/lib/api";
import type { Proof } from "@/lib/types";

type Doc = { found: number; portal_found: number };

export default function JudgePage() {
  const { data: p, error } = useApi<Proof>("/api/proof");
  const { data: doc } = useApi<Doc>("/api/doctor");
  const { data: sc } = useApi<{ districts: unknown[] }>("/api/scale");
  if (!p) return <Shell title="Check it yourself"><ErrorNote error={error} /></Shell>;
  const h = p.headline;
  const D = p.policies.D, B = p.policies.B;
  const rows: { name: string; claim: string; go: [string, string][]; limit: string }[] = [
    {
      name: "Problem and idea", claim: "A shared solar pump sleeps most of the day while the next field burns diesel. Book water by missed call; give the spare sun to the mill.",
      go: [["/", "Follow Ramesh's day"], ["/phone", "Give a missed call and press 1"]],
      limit: "Personas are composites. Maithili and Bhojpuri wording still needs a native speaker.",
    },
    {
      name: "Architecture and design", claim: "The Altivar drive is both the hand and the meter. Plans keep running when the network does not, and no agent can spend water or money without a yes.",
      go: [["/drive", "Break the drive and follow the fix"], ["/trace", "Read every agent step"]],
      limit: "The drive is simulated from the published register map. No hardware has been run.",
    },
    {
      name: "Impact, measured", claim: `${fmt.n(h.utilisation_D_kwh_per_kwp)} kWh per kWp put to work against ${fmt.n(h.utilisation_B_kwh_per_kwp)} for first-come hourly sales (${fmt.signedPct(h.utilisation_gain_vs_B)}), and ₹${h.farmer_rs_per_m3_D.toFixed(2)} a m³ against ₹${h.farmer_rs_per_m3_B.toFixed(2)}. Simulated on weather years the models never saw.`,
      go: [["/lab", "See every band and the negative results"]],
      limit: "Most of the gain comes from the extra loads, not the planner. Diesel avoided is about level with the baseline, because the water cap holds some back.",
    },
    {
      name: "Feasible and affordable", claim: `Try ${sc?.districts.length ?? "several"} districts on their real sun, your own prices and your own doubts.${doc ? ` Slow pump faults found early: ${fmt.pct(doc.found)}, against ${fmt.pct(doc.portal_found)} for a daily-energy alert.` : ""}`,
      go: [["/rollout", "Change the costs"], ["/drive#doctor", "Try the Pump Doctor"]],
      limit: `With a paid operator the owner earns ${fmt.rs(D.owner_fpo_income_rs.p50)}, less than the ${fmt.rs(B.owner_fpo_income_rs.p50)} from selling by the hour. It works when the owner or group runs it. No supplier quote for the kit yet.`,
    },
    {
      name: "Sustainability", claim: "The village's water budget is a hard limit, kept in every simulated season. Every litre carries a receipt anyone can verify.",
      go: [["/ledger", "Verify the whole chain"], ["/cluster", "Three pumps, one water table"]],
      limit: "The cap value and the block's groundwater category are assumptions until confirmed for the pilot site.",
    },
  ];
  return (
    <Shell title="Check it yourself">
      <ol className="flex max-w-[980px] flex-col">
        {rows.map((r) => (
          <li key={r.name} className="grid gap-x-8 gap-y-3 border-t border-soil py-7 md:grid-cols-[220px_minmax(0,1fr)]">
            <h2 className="h-lead">{r.name}</h2>
            <div>
              <p className="text-[17px] leading-relaxed">{r.claim}</p>
              <p className="mt-4 flex flex-wrap gap-2.5">
                {r.go.map(([href, label]) => <Link key={label} href={href} className="inline-flex min-h-11 items-center rounded-full bg-sun px-5 text-[15px] font-medium text-ink hover:bg-sun-deep">{label}</Link>)}
              </p>
              <p className="mt-4 text-[14px] text-mist"><b className="font-semibold text-fog">What it does not show:</b> {r.limit}</p>
            </div>
          </li>
        ))}
      </ol>
      <p className="border-t border-soil pt-5 text-[14px] text-mist">Pressed the wrong thing? Use Reset in the top bar; the demo day starts again for everyone.</p>
    </Shell>
  );
}
