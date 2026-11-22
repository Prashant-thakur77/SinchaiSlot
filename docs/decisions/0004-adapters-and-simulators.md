# 0004 Adapters, simulators and where the agent loop runs

**Decision.** Every external service (LLM, speech, IVR, WhatsApp, UPI, the drive itself) sits behind
an adapter interface with a local simulator, and the simulator is the default. The agent loop runs
in-process on the Messages API (manual tool loop) behind a provider interface, with an offline
rule-based provider as the default and Claude as an optional provider (`LLM_PROVIDER=anthropic`).

**Why.**
- The definition of done requires `docker compose up`, `make seed`, `make demo` with no paid keys.
- Field pumps lose connectivity; the edge must keep working offline and the farmer channel must
  degrade to IVR/USSD without data.
- Keeping the agent loop in our process lets one confirmation gate and one trace store cover both
  providers, and keeps the LLM off the real-time control path: the edge controller and the MILP are
  deterministic; agents only call typed tools.
- Confirmation of anything that spends money, water or energy is decided by deterministic yes/no
  detection on the farmer's next turn, never by the model.

**Claude provider settings.** `claude-opus-5-5`, effort `low` for short spoken replies, server-side
refusal fallbacks enabled (`fallbacks: "default"`), strict tool schemas, farmer text wrapped in
`<farmer_message>` tags, flagged prompt-injection input routed to the rules path instead.
