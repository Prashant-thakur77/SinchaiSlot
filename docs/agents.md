# Agents

| Agent | Users | Tools (typed, role-checked) |
|---|---|---|
| Saathi | farmers (IVR, WhatsApp, USSD, web) | find_slots, quote_price, book_slot*, cancel_slot*, my_bookings, get_balance, pay_link, check_schemes, report_issue, explain_plan_change, list_sellers, book_seller*, harvest_offer, pay_after_harvest*, vistaar_handoff, water_quality, transfer_options, transfer_booking* |
| Saur Mitra Copilot | operator | today_plan, cash_book, drive_status, diagnose, log_maintenance*, request_part*, reset_fault*, record_payment*, apply_soil_card, cluster_overview, suggest_transfers, transfer_booking*, pump_health |
| Surya Planner | planner, operator | run_forecast, solve_plan, what_if, explain_diff |
| Jal Prahari | all | budget_status, awd_advice |
| Rasid Auditor | funders | ledger_summary, verify_ledger, audit_ledger, claim_pack, pump_passport, recharge_plan |
| Hisaab | funders, FPO | hisaab_ask, query_ledger_sql (one SELECT, allow-listed tables, LIMIT forced, read-only transaction) |

`*` = needs human confirmation. The runtime never runs these on a model's say-so: it reads the action
back in the user's language and runs it only on a clear yes in the next turn.

## Guards
- Farmers act only on their own account (the tool layer overrides `farmer_id`).
- Bookings never exceed the plot's FAO-56 crop-water need.
- Offers are tokens: on yes, exactly the offered plan is adopted; if the plan changed in between, the
  farmer gets a fresh offer.
- Prompt-injection patterns are flagged and never sent to the hosted LLM.
- After two turns it cannot understand, Saathi hands over to the Saur Mitra.
- Every run and tool call is stored (`/api/traces`, Agent trace screen).

## Providers
`rules` (default, offline, deterministic) or an optional hosted LLM (`LLM_PROVIDER=anthropic`).

## Evaluation
`make evals`: 204 held-out scripted conversations (Hindi, Maithili, Bhojpuri, English, romanised,
code-mixed), a separate dev split, simulated ASR noise sweep, optimiser benchmark. Results in
`reports/evals.json`, with the first strictly held-out run kept separately from the post-fix run.

## MCP
`uv run sinchaislot-mcp` exposes every tool over MCP (stdio); confirm-tools require `confirmed=true`.
