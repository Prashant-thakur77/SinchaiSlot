# One image for every Python service (api, drive simulator, edge simulator, proof runner).
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY packages ./packages
COPY services ./services
COPY docs/schneider/register_map.yaml docs/schneider/fault_codes.yaml ./docs/schneider/
COPY reports/proof.json reports/evals.json reports/story_replay.json reports/

RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "sinchai_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
