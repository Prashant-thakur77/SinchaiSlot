"use client";

import { useState } from "react";
import { Shell } from "@/components/Shell";
import { ErrorNote, Panel } from "@/components/ui";
import { useApi } from "@/lib/api";

type Run = {
  id: string;
  agent: string;
  channel: string;
  user_ref: string | null;
  provider: string;
  input: string;
  output: string;
  status: string;
  language: string;
  latency_ms: number;
  at: string;
  tool_calls: { name: string; args: Record<string, unknown>; result: Record<string, unknown>; confirm: boolean; confirmed: boolean | null; error: string | null; ms: number }[];
};

const AGENTS = ["all", "saathi", "copilot", "surya_planner", "rasid_auditor", "hisaab", "api"];

export default function TracePage() {
  const [agent, setAgent] = useState("all");
  const { data, error } = useApi<Run[]>(`/api/traces?limit=80${agent === "all" ? "" : `&agent=${agent}`}`, 3000);
  const [sel, setSel] = useState<string | null>(null);
  const run = data?.find((r) => r.id === sel) ?? data?.[0];
  return (
    <Shell title="Agent trace">
      <ErrorNote error={error} />
      <p className="mb-3 max-w-3xl text-[13px] text-mist">
        Agents plan, explain and talk; deterministic code executes. Every run is stored with its input, each typed tool call, whether it
        needed a human yes, and latency. Tools that spend money, water or energy show the confirmation that released them.
      </p>
      <div className="mb-3 flex flex-wrap gap-1.5" role="tablist" aria-label="Filter by agent">
        {AGENTS.map((a) => (
          <button key={a} role="tab" aria-selected={agent === a} onClick={() => setAgent(a)} className={`rounded-full px-3 py-1 text-[12px] ${agent === a ? "bg-sun text-ink" : "bg-night-2 text-fog hover:bg-night-3"}`}>
            {a.replace("_", " ")}
          </button>
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
        <Panel title={`Runs (${data?.length ?? 0})`}>
          <ol className="flex max-h-[70vh] flex-col overflow-y-auto">
            {(data ?? []).map((r) => (
              <li key={r.id}>
                <button onClick={() => setSel(r.id)} className={`w-full rounded-md px-2.5 py-2 text-left ${run?.id === r.id ? "bg-night-3" : "hover:bg-night"}`}>
                  <div className="flex items-center gap-2 text-[11px] text-mist">
                    <span className="num">{r.at.slice(11, 19)}</span>
                    <span className="text-sun">{r.agent === "api" ? "direct tool call" : r.agent}</span>
                    {r.channel !== "api" && <span>{r.channel}</span>}
                    {r.status !== "ok" && <span className="text-fault">{r.status}</span>}
                    <span className="num ml-auto">{r.latency_ms} ms</span>
                  </div>
                  <div className="deva truncate text-[13px]">{r.input || "(callback opening)"}</div>
                  <div className="num truncate text-[11px] text-mist">{r.tool_calls.map((c) => c.name).join(" → ") || "no tools"}</div>
                </button>
              </li>
            ))}
          </ol>
        </Panel>
        {run && (
          <Panel title={<span className="num">{run.id}</span>} right={<span className="text-[11px] text-mist">{run.provider} · {run.language} · {run.user_ref ?? "–"}</span>}>
            <div className="flex flex-col gap-4">
              <div>
                <div className="text-[11px] text-mist">Input</div>
                <p className="deva mt-1 text-[14px]">{run.input}</p>
              </div>
              {/* Departure-board summary of the run */}
              <div className="grid grid-cols-3 gap-px overflow-hidden rounded-md border border-soil bg-soil text-[11px]">
                {[
                  ["AGENT", run.agent === "api" ? "direct" : run.agent.replace("_", " ")],
                  ["TOOLS", String(run.tool_calls.length)],
                  ["TOTAL", `${run.latency_ms} ms`],
                ].map(([k, v]) => (
                  <div key={k} className="bg-night px-3 py-2">
                    <div className="num tracking-wider text-mist">{k}</div>
                    <div className="num mt-0.5 text-[15px] text-sun">{v}</div>
                  </div>
                ))}
              </div>
              <ol className="relative ml-2 flex flex-col gap-3 border-l border-soil pl-4">
                {run.tool_calls.map((c, i) => (
                  <li key={i} className="relative">
                    <span className={`absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full ${c.error ? "bg-fault" : c.confirm ? (c.confirmed ? "bg-leaf" : "bg-sun") : "bg-water"}`} />
                    <div className="flex flex-wrap items-center gap-2 text-[12px]">
                      <code className="num text-sun">{c.name}</code>
                      {c.error && <span className="text-fault">{c.error}</span>}
                      <span className={`num ml-auto rounded px-1.5 text-[10px] tracking-wider ${c.error ? "bg-fault/15 text-fault" : c.confirm ? (c.confirmed ? "bg-water/15 text-water" : "bg-sun/15 text-sun") : "bg-night-3 text-fog"}`}>
                        {c.error ? "FAILED" : c.confirm ? (c.confirmed ? "RELEASED BY YES" : "HELD") : "DONE"}
                      </span>
                      <span className="num w-16 text-right text-mist">{c.ms} ms</span>
                    </div>
                    <div className="mt-1 h-1 rounded-full bg-night-3" aria-hidden>
                      <div className={`h-1 rounded-full ${c.error ? "bg-fault" : "bg-sun/70"}`} style={{ width: `${Math.max(2, (c.ms / Math.max(1, ...run.tool_calls.map((x) => x.ms))) * 100)}%` }} />
                    </div>
                    <pre tabIndex={0} className="num mt-1 max-h-56 overflow-auto rounded bg-night p-2 text-[11px] text-fog">{JSON.stringify({ args: c.args, result: c.result }, null, 1)}</pre>
                  </li>
                ))}
              </ol>
              <div>
                <div className="text-[11px] text-mist">Reply</div>
                {(() => {
                  try {
                    const j = run.output.trim().startsWith("{") ? JSON.parse(run.output) : null;
                    if (j) return <pre tabIndex={0} className="deva mt-1 max-h-56 overflow-auto rounded bg-night p-2 text-[12px] text-fog">{JSON.stringify(j, null, 2)}</pre>;
                  } catch {}
                  return <p className="deva mt-1 text-[14px]">{run.output}</p>;
                })()}
              </div>
            </div>
          </Panel>
        )}
      </div>
    </Shell>
  );
}
