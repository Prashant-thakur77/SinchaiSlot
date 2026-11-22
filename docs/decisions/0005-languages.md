# 0005 Languages and microcopy review

Saathi speaks Hindi, Maithili, Bhojpuri and English. All farmer-facing phrases live in
`services/api/sinchai_api/agents/i18n.py` and the keyword lists in `agents/nlu.py`.

**Status: draft wording.** Hindi strings were written for the prototype; Maithili and Bhojpuri
strings are best-effort drafts. PLAN.md 9.4 requires review by a native speaker before any phrase is
played to a farmer. Until then the demo labels these strings as draft.

**Choice of default.** When the language cannot be detected, Saathi replies in the farmer's stored
language (per-farmer memory), else Hindi.
