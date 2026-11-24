"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export const API = process.env.NEXT_PUBLIC_API_BASE ?? "";

export async function getJSON<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json() as Promise<T>;
}

export async function postJSON<T>(path: string, body: unknown = {}, token?: string): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    let msg = `${r.status}`;
    try {
      msg = (await r.json()).detail ?? msg;
    } catch {}
    throw new Error(msg);
  }
  return r.json() as Promise<T>;
}

/** Fetch a JSON resource, optionally re-fetching on an interval. */
export function useApi<T>(path: string | null, refreshMs = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const reload = useCallback(async () => {
    if (!path) return;
    try {
      const d = await getJSON<T>(path);
      setData(d);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [path]);
  useEffect(() => {
    const first = setTimeout(reload, 0);
    const t = refreshMs ? setInterval(reload, refreshMs) : undefined;
    return () => {
      clearTimeout(first);
      if (t) clearInterval(t);
    };
  }, [reload, refreshMs]);
  return { data, error, loading, reload, setData };
}

export type ServerEvent = { kind: string; ts: string; [k: string]: unknown };

/** Subscribe to the platform's server-sent events (plan, telemetry, receipt, callback, nowcast, edge). */
export function useEvents(onEvent: (e: ServerEvent) => void, kinds: string[]) {
  const cb = useRef(onEvent);
  useEffect(() => {
    cb.current = onEvent;
  }, [onEvent]);
  const key = kinds.join(",");
  useEffect(() => {
    let es: EventSource | null = null;
    let closed = false;
    const open = () => {
      es = new EventSource(`${API}/api/events`);
      for (const k of key.split(",")) {
        es.addEventListener(k, (m) => {
          try {
            cb.current({ kind: k, ...(JSON.parse((m as MessageEvent).data) as object) } as ServerEvent);
          } catch {}
        });
      }
      es.onerror = () => {
        es?.close();
        if (!closed) setTimeout(open, 2000);
      };
    };
    open();
    return () => {
      closed = true;
      es?.close();
    };
  }, [key]);
}

// Public on purpose: the hosted demo holds simulated data only and visitors act as the operator.
export const OPERATOR_TOKEN = process.env.NEXT_PUBLIC_DEMO_OPERATOR_TOKEN ?? "dev-operator-token";

export const fmt = {
  n: (x: number | null | undefined, d = 0) =>
    x === null || x === undefined || Number.isNaN(x) ? "–" : x.toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d }),
  pct: (x: number | null | undefined, d = 0) => (x === null || x === undefined ? "–" : `${(x * 100).toFixed(d)}%`),
  signedPct: (x: number | null | undefined, d = 0) =>
    x === null || x === undefined ? "–" : `${x >= 0 ? "+" : "−"}${Math.abs(x * 100).toFixed(d)}%`,
  rs: (x: number | null | undefined, d = 0) => (x === null || x === undefined ? "–" : `₹${fmt.n(x, d)}`),
};
