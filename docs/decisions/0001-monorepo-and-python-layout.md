# 0001 Monorepo and Python layout

**Decision.** One root `pyproject.toml` (uv, Python 3.12) builds every Python service package
(`services/*/sinchai_*`, `packages/schemas/sinchai_schemas`) into one environment. The web app is a
pnpm workspace under `apps/web` with shared design tokens in `packages/ui`.

**Why.** The services share schemas, constants and the simulator; one environment keeps `make test`
and `make proof` to a single command and removes cross-package version drift during the hackathon.
Each service still owns its own package and can be split into its own image later.
