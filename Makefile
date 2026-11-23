# SinchaiSlot. Every target runs with no paid API keys.
SHELL := /bin/bash
UV := env -u VIRTUAL_ENV uv run
COMPOSE := docker compose

.PHONY: help dev up down seed demo soak proof proof-quick publish ingest test test-py test-web evals lint fmt web mcp drive-sim api

help:
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

dev: ## Run the whole stack in Docker (web :3000, api :8000)
	$(COMPOSE) up --build

up: ## Same as dev, detached
	$(COMPOSE) up --build -d

down:
	$(COMPOSE) down

seed: ## Build the demo database (Docker if running, else local SQLite)
	@if $(COMPOSE) ps --status running api 2>/dev/null | grep -q api; then \
		$(COMPOSE) exec api python -m sinchai_api.seed; else $(UV) python -m sinchai_api.seed; fi

demo: ## Play the scripted demo (missed call, booking, 13:40 cloud, fault fix, receipts) in the terminal
	$(UV) python -W ignore -m sinchai_api.demo_script

soak: ## Run the cloud-at-13:40 scenario 10 times and check it is identical and correct each time
	$(UV) python -W ignore -m sinchai_api.demo_script --soak 10

ingest: ## Re-download NASA POWER and Open-Meteo snapshots
	$(UV) python -m sinchai_data.ingest

proof: ## Regenerate reports/proof.json and reports/figures from real data
	$(UV) python -W ignore -m sinchai_sim.proof

publish: ## Render README, form notes and the deck from proof.json and evals.json
	$(UV) python -m sinchai_sim.publish
	@if [ -d apps/web/node_modules ]; then cd apps/web && node scripts/deck-pdf.mjs ../../submission/deck/deck.html ../../submission/deck/deck.pdf; fi

proof-quick: ## Small proof run for CI
	$(UV) python -W ignore -m sinchai_sim.proof --quick

test: test-py test-web ## All tests

test-py: ## Python unit, invariant, edge-offline and API tests
	$(UV) pytest tests

test-web: ## Playwright end-to-end and accessibility tests (needs `pnpm install` in apps/web)
	@if [ -d apps/web/node_modules ]; then cd apps/web && pnpm test:e2e; else echo "apps/web not installed; skipping"; fi

evals: ## Agent eval suite (held-out scripted interactions), ASR WER, optimiser benchmark
	$(UV) python -W ignore -m evals.run

film-capture: ## Record every product shot for the video from the running stack (docker compose up first)
	cd apps/web && node scripts/capture-film.mjs ../../submission/video/capture.json

lint: ## ruff + mypy + eslint
	$(UV) ruff check services packages tests evals
	$(UV) mypy services/planner services/jalprahari services/rasid --ignore-missing-imports
	@if [ -d apps/web/node_modules ]; then cd apps/web && pnpm lint; fi

fmt:
	$(UV) ruff format services packages tests evals

api: ## Run the API locally on :8000
	$(UV) uvicorn sinchai_api.main:app --port 8000 --reload

web: ## Run the web app locally on :3000
	cd apps/web && pnpm dev

drive-sim: ## Run the Altivar Modbus simulator on :5020
	$(UV) python -m sinchai_devices.sim_server --port 5020 --profile clear --speed 60

mcp: ## Run the MCP server (stdio)
	$(UV) sinchaislot-mcp
