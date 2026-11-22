# SinchaiSlot web

Next.js (App Router) app: the story page, the dashboards and the Saur Mitra PWA.

```bash
pnpm install
pnpm dev            # http://localhost:3000 (expects the API on :8000; /api is proxied)
pnpm build && pnpm start
pnpm test:e2e       # Playwright + axe; needs the API and the web app running (BASE_URL)
```

Screens: `/` story · `/twin` Village Twin · `/planner` Surya Planner · `/phone` Saathi phone simulator ·
`/drive` Altivar Solar drive · `/ledger` Rasid · `/lab` Prayogshala proof · `/trace` agent trace ·
`/hisaab` ledger questions · `/mitra` Saur Mitra app (offline-capable).
Design system: `../../.design/DESIGN.md`.
