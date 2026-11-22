import type { ToolCall } from "@/lib/types";

export function ToolList({ calls }: { calls: ToolCall[] }) {
  return (
    <ol className="flex flex-col gap-2">
      {calls.map((c, i) => (
        <li key={i} className="rounded-md border border-soil bg-night p-2.5">
          <div className="flex flex-wrap items-center gap-2 text-[12px]">
            <code className="num text-sun">{c.tool}</code>
            {c.needs_confirmation && <span className="rounded bg-sun/15 px-1.5 text-sun">needs confirmation</span>}
            {c.confirmed && <span className="rounded bg-leaf/15 px-1.5 text-leaf">confirmed by farmer</span>}
            {c.error && <span className="rounded bg-fault/15 px-1.5 text-fault">{c.error}</span>}
            <span className="num ml-auto text-mist">{c.latency_ms} ms</span>
          </div>
          <details className="mt-1">
            <summary className="cursor-pointer text-[11px] text-mist">args and result</summary>
            <pre tabIndex={0} className="num mt-1 max-h-48 overflow-auto whitespace-pre-wrap text-[11px] text-fog">{JSON.stringify({ args: c.args, result: c.result }, null, 1)}</pre>
          </details>
        </li>
      ))}
    </ol>
  );
}
