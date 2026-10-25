# AGENTS.md

Setup quirks and conventions for this repo. Read this before changing
`app/models.py` or adding a new agent. Product spec is `PLAN.md` - this
file is implementation notes, not the spec.

## Environment

- Python 3.11+ (built/tested on 3.15, `./.venv`). Dependencies in
  `requirements.txt`, pinned to `google-genai>=2.30.1`.
- `GEMINI_API_KEY` lives in `.env` at the repo root (gitignored). Loaded via
  `python-dotenv` in `app/models.py`. Never commit `.env`.

## Model roster (`app/models.py`)

- `LEAD = "gemini-4-argon"` — orchestrator, scribe, verifier, agent_builder.
- `FAST = "gemini-3.8-flash"` — intake, prescription, emails, and the
  baseline for any unlisted role.
- Every call goes through `call_model(role, input_text, thinking_level, ...)`.
  **Never pass `temperature`, `top_p`, `top_k`, or `thinking_budget`** —
  only `thinking_level` (`minimal`/`low`/`medium`/`high`), set per call
  inside `generation_config`.
- HTTP timeout is set via `genai.Client(http_options={"timeout": 1_200_000})`
  (ms) = 20 minutes.
- `call_antigravity()` runs the real Antigravity managed agent
  (`antigravity-preview-09-2026`) with `agent_config={"type":
  "antigravity", "model": ...}` - used by `agent_builder`, not by the
  visit pipeline.

## Data model (`app/storage.py`) — "visit", not "case"

This project was rebuilt from an earlier "case"-based prototype to match
`PLAN.md`'s screen spec. Everything is now a **visit**:
- `data/panel/panel.json` — patient panel (chart data), auto-seeded from
  `data/demo/panel_seed.json` on first run. Currently just the two demo
  patients in PLAN.md (Margaret Smith, Jhonatan) - all synthetic.
- `data/visits/<visit_id>.json` — one file per visit: booking info,
  matched patient record, intake summary, transcript, physician plan, and
  `documents` (scribe/prescription/emails, each with its own
  verification_rounds + approval record).
- `data/demo/flags.json` — demo switches, currently just
  `DEMO_PLANTED_ERROR` (see below). Toggle via the UI checkbox or
  `POST /api/demo/flags/DEMO_PLANTED_ERROR`.
- `data/activity.jsonl` — append-only activity log, one JSON line per
  agent/physician/system action with a timestamp.
- `data/tools/registry.json` — agent-builder "My tools" registry (phase 2,
  not built yet as of this note).
- `runs/<visit_id>_<run_id>.json` — full pipeline transcript per visit run
  (superset of what's in `documents`, kept for audit).

## Verification loop (`app/verify.py`) — blocking, not advisory

Unchanged in spirit from the prior build, now visit-scoped. For each of
scribe, prescription, and emails (intake is NOT verified - see below):

1. The agent drafts the document (`module.build_input(visit)`).
2. `verifier.check()` — an **independent** gemini-4-argon call,
   `thinking_level=high`, structured JSON via `response_format` — checks
   it sentence-by-sentence against ground truth (patient chart + whatever
   context that agent was given) and returns `{passed, failures:
   [{sentence, reason}]}`.
3. A failure sends the exact failing sentences + reasons back to the
   *same* agent to rewrite the full document.
4. Repeat. **Up to 3 rounds total.** If round 3 still fails, the step is
   `resolved: false` and the visit gets `needs_manual_review: true`.

Every round (draft + verdict) is kept on `document.verification_rounds`
and shown in the UI. Intake is generated once, eagerly, at booking time -
it's reference material for the physician (left panel), not one of the
three reviewed/approved documents, so it skips the loop by design.

### DEMO_PLANTED_ERROR

When this flag is on, the very first scribe draft for a visit whose
patient name is "Margaret Smith" gets the literal sentence "Potassium is
elevated at 5.4." appended before it's ever verified
(`app.orchestrator.PLANTED_ERROR_TEXT`, applied by
`run_with_verification`'s `inject_error_text` param). Her chart's actual
latest potassium (2026-09-12) is 4.3 - normal; 5.4 is an old, resolved
reading from 2025-08-20. The verifier has her full chart as ground truth,
so it should catch and reject the sentence, forcing a rewrite. This is
the concrete proof that the verifier blocks instead of rubber-stamping.

## Approval queue and send enforcement (`app/storage.py`)

"Nothing sends without an approval record" is enforced in
`mark_document_sent()`, not just in the UI: it raises `PermissionError`
if `document["approval"]["status"] != "approved"`, and the route
(`app/routes/approvals.py`) turns that into an HTTP 403. The UI's "Send
(simulated)" button is also disabled client-side until approved, but the
server-side check is the real enforcement - hitting the endpoint directly
without an approval record fails.

Verifier passing (`resolved: true`) and physician approval are two
separate gates: a document can pass every verifier round and still get
rejected by the physician, and a document that never resolves after 3
rounds can still be manually approved by the physician (with
`needs_manual_review` having already told them to look closely).

## Prescriptions are simulated, not real

`prescription` documents are labeled "SIMULATED FAX" in the UI
(`DOC_LABELS` in `static/app.js`) and "sent" only flips a flag on the
visit record — there is no real fax/pharmacy/payer integration anywhere
in this codebase.

## What's mocked

- `tools/clinical.py::check_drug_interactions` — fake/deterministic drug
  interaction data, not a real database.
- `data/demo/panel_seed.json` — synthetic patients only.
- Sending (fax/email) — simulated, flips a flag, nothing leaves the app.

## Running it

```
./.venv/bin/uvicorn app.main:app --reload --port 8000
```

Then open http://localhost:8000. `/test-argon` is a plain GET endpoint
for a quick sanity check outside the UI.

## Build status (see PLAN.md for the order)

1. ✅ Margaret's full visit flow with the verifier loop (Visits, Approval
   queue, Activity log tabs are functional)
2. ⬜ Agent builder (tab exists as a placeholder)
3. ⬜ Results batch (tab exists as a placeholder)
4. ⬜ Practice setup and booking page (tabs exist as placeholders; visits
   are currently created via `POST /api/booking` directly, not through a
   built UI form)
