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
- `data/tools/registry.json` — agent-builder "My tools" registry.
- `data/demo/synthetic_panel_2500.csv` + `synthetic_panel_meta.json` —
  the fixed 2,500-patient synthetic panel used to test agent-built tools,
  generated once with a seeded RNG (`seed=42`) so `true_diabetic_count`
  in the meta file is a stable ground truth. Columns: id, name, age, sex,
  conditions (`;`-separated), last_a1c, visits_last_2yr.
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

### Shared grounding (`app/agents/base.py`)

Every agent's `build_input()` and the verifier's ground-truth context
both start from `patient_record_block()` (full name, DOB, conditions,
meds, labs, vitals, pharmacy) and `physician_block()` (the physician name
from practice settings). No agent is ever left guessing an identifier -
they either state it exactly or the verifier catches the omission.

### Stricter rule: no invented instructions

Beyond the baseline hallucination/contradiction check, the verifier
prompt (`prompts/verifier.md`) enforces a document-scoped rule: for
`prescription` and `emails`, every sentence must trace to something the
physician actually wrote in the plan or said in the transcript - no
precautions, dosing tips, or follow-up advice invented even if clinically
reasonable. For `scribe`, this stricter rule applies only to the note's
Plan section; Subjective/Objective/Assessment may still synthesize
reasonably from context. Missing name/DOB is checked as an omission for
`scribe` and `prescription` only - `emails` deliberately omits DOB and
greets by first name, so the verifier is told not to require it there.

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

## Agent builder (`app/agents/agent_builder.py`) — real, not mocked

Calls the real Antigravity managed agent (`antigravity-preview-09-2026`)
with `agent_config={"type": "antigravity", "model": "gemini-4-argon"}` in
a real sandboxed Linux environment: it writes `panel.csv` from the
synthetic 2,500-patient fixture, writes a tool, writes a test against
hand-built fake rows, runs the test, runs the real tool against the real
panel, and reports back. When the description mentions "diabet", the
reported `FINAL_COUNT` is checked against `synthetic_panel_meta.json`'s
`true_diabetic_count` and stored as `count_matches`.

**Quirk worth knowing**: a single call very often comes back
`status: "incomplete"` with **empty** `output_text` even though the real
work (writing the tool, testing it, running it against the panel)
already succeeded - inspecting the interaction's raw `steps` shows the
code execution genuinely ran and produced real results; Antigravity's
per-turn step budget just runs out before it writes the wrap-up summary
that contains our `FINAL_COUNT`/`TESTS_PASSED` markers. This is not a
`max_total_tokens` problem (observed token usage was well under the
500k cap). The fix, in `run()`: if `output_text` comes back empty, send a
short follow-up turn in the *same* sandbox (`previous_interaction_id` +
`environment_id` from the first call) asking it to just report what it
already found - up to `MAX_FOLLOWUPS` (3) times. Don't "fix" this by only
raising `max_total_tokens` - that alone did not resolve it in testing.

Real cost/time: a run against the full panel took several minutes and
real API usage in testing (Google's docs cite roughly $0.30-$3+ per run,
and this one does more work than their baseline examples).

## What's mocked

- `data/demo/panel_seed.json` — synthetic patients only.
- `data/demo/synthetic_panel_2500.csv` — synthetic panel, not real
  patients.
- Sending (fax/email) — simulated, flips a flag, nothing leaves the app.
- No real e-prescribing or payer submission anywhere in this codebase.

## Running it

```
./.venv/bin/uvicorn app.main:app --reload --port 8000
```

Then open http://localhost:8000. `/test-argon` is a plain GET endpoint
for a quick sanity check outside the UI.

## Build status (see PLAN.md for the order)

1. ✅ Margaret's full visit flow with the verifier loop (Visits, Approval
   queue, Activity log tabs are functional)
2. ✅ Agent builder (real Antigravity + gemini-4-argon, tested against the
   synthetic 2,500-patient panel)
3. ⬜ Results batch (tab exists as a placeholder)
4. ⬜ Practice setup and booking page (tabs exist as placeholders; visits
   are currently created via `POST /api/booking` directly, not through a
   built UI form)
