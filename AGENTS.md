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

### Live progress + persistence

Tool records persist to `data/tools/registry.json` from the moment a
build *starts* (`storage.start_tool_build`), not just on completion, so
a build survives a server restart and "My tools" always reflects disk
state.

Progress shown in the UI is real, not a simulated spinner. We tried two
approaches:
- `background=True` + polling `client.interactions.get()` — **does not
  work for progress**: `interaction.steps` stays empty the whole time
  `status == "in_progress"`, confirmed by direct inspection. There is
  nothing to derive a label from until the call is already done.
- `stream=True`, consumed in a background `threading.Thread`
  (`app.agents.agent_builder._run_build`) — works. Each `step.start`
  event names the real step (`write_to_file`, `code_execution_call`,
  etc.), mapped to a human label (`_label_for_step`) and written to the
  tool record immediately. The UI polls `GET /api/tools/{id}/status`
  every 3s, which is now just a disk read (`poll_build`) - no extra API
  calls, since the thread already keeps storage current.

Note the first label update can take a while to arrive for this
specific tool (large embedded panel.csv means a long prefill before the
first step) - that's real latency, not a stuck mechanism.

## Results batch (`app/results.py`) — Phase 3

10 synthetic cases (`data/demo/results_cases.json`, all synthetic) x 3
document types (note/scribe, prescription, prior_auth - `prior_auth` was
recreated just for this benchmark; it's not part of the live visit
pipeline) x 3 methods, run concurrently with a `ThreadPoolExecutor`
(`MAX_WORKERS=15`): one thread per (case, method) pair, each running its
own sequential 3-document pipeline (note -> prescription -> prior_auth,
since later docs depend on earlier ones).

- **Flash baseline** - one `gemini-3.8-flash` call per document, generic
  prompt, no specialized grounding/prompt engineering.
- **Argon agents** - one `gemini-4-argon` call per document using the
  real specialized prompts (`prompts/scribe.md` etc.) and grounding
  (`patient_record_block`/`physician_block`), single draft, no verifier.
- **Argon agents + verifier** - the real `app.verify.run_with_verification`
  loop, up to 3 rounds.

**Errors are measured the same way across all three methods** so the
comparison is fair: baseline and Argon-agents-only have no internal
verifier, so each of their final documents gets one independent
`verifier.check()` grading pass after the fact (`_grade()`) - this is
the same sentence-level check the real pipeline uses, just applied
externally as a grader rather than internally as a gate.
"errors_caught_total" is correctly 0 for both, since no verifier ran
during their generation. For the verified method, "errors found" is
round 1's failure count (a fair stand-in for "what a single first draft
would have contained," comparable to the other two methods' single
draft), and "errors caught" is how many of those got fixed by the end of
the loop.

Progress is a plain completed/total counter
(`storage.bump_results_progress`, incremented after each of the 90
document generations) guarded by a `threading.Lock` since many worker
threads increment it concurrently - simpler than the agent-builder's
step-event streaming because `call_model`/`run_with_verification` don't
expose incremental sub-steps the way Antigravity does.

"Total tokens" is reported as the cost column, not a dollar estimate -
there's no verified real pricing to cite for these model names, so a
token count is the honest, comparable proxy rather than a fabricated
dollar figure.

**Actual result from one real run** (10 cases, all synthetic, ~13 min
wall-clock with 15-way concurrency): Flash baseline averaged 4.63
errors/doc; Argon agents (specialized prompts, no verifier) cut that to
0.9/doc even without verification; Argon agents + verifier caught all 24
round-1 errors it found (errors_caught_total == round1 errors found),
at roughly 1.8x the baseline's token cost and ~5x the per-document
latency. Re-running will produce different exact numbers (live model
calls), but the shape of the result - baseline worst, specialized
prompts alone much better, verifier closing the remaining gap at a real
time/cost premium - is the point being demonstrated.

## What's mocked

- `data/demo/panel_seed.json` — synthetic patients only.
- `data/demo/synthetic_panel_2500.csv` — synthetic panel, not real
  patients.
- Sending (fax/email) — simulated, flips a flag, nothing leaves the app.
- No real e-prescribing or payer submission anywhere in this codebase.

## Scheduling (`app/scheduling.py`)

`available_slots()` parses the practice's free-text `hours` field (e.g.
"Mon-Fri 9am-5pm") with a couple of regexes - it's not a real calendar
system, just enough to generate 20-minute slots for the next 3 days,
skip past times on today, and hide slots any existing visit already has
as `appointment_time`. If the hours string doesn't parse, it silently
falls back to Mon-Fri 9-5. `list_visits()` sorts scheduled visits by
`appointment_time` ascending; unscheduled visits (anything not booked
through the scheduling step, e.g. Margaret's demo case) sort after,
newest first.

## Simulated payment

`POST /api/visits/{id}/pay` sets `payment_status` to `"paid
(simulated)"` and logs the activity entry as **"billing agent"** - no
real payment processor anywhere. `GET /api/earnings` sums `paid_amount`
across visits with that status for the Practice setup page's earnings
line. The booking page's checkout step has no card fields by design.

## ngrok + start_demo.sh

`GET /api/ngrok-url` reads ngrok's own local status API
(`127.0.0.1:4040/api/tunnels`), not a guess - it only returns a URL when
ngrok is actually running, so the Practice setup QR code is correct
regardless of what URL the dashboard itself is being viewed from.
`start_demo.sh` starts the server, ngrok, and `caffeinate -dims`
together, waits for both the server and the tunnel to be ready, and
prints the public link; Ctrl+C tears all three down via a trap. ngrok
itself needs your own free account's authtoken
(`./.bin/ngrok config add-authtoken <token>`, one-time) - there's no way
around that, it's tied to your ngrok account, not something this repo
can bundle.

## Reset demo (`storage.reset_demo`)

Clears every visit file except Margaret's demo case, which is restored
from a fixed seed (`data/demo/margaret_visit_seed.json`) rather than
regenerated live - regenerating would cost real API calls and a couple
of minutes every time, and wouldn't be deterministic. Deliberately
leaves the tools registry, results run, and practice settings alone;
those aren't part of what "reset" means here. If you change Margaret's
demo flow (prompts, pipeline, etc.) in a way that should be reflected in
the reset state, regenerate the seed by booking + approving her visit
again through the real pipeline and copying the resulting
`data/visits/<id>.json` over `data/demo/margaret_visit_seed.json`.

## Running it

```
./.venv/bin/uvicorn app.main:app --reload --port 8000
```

Then open http://localhost:8000. `/test-argon` is a plain GET endpoint
for a quick sanity check outside the UI. For a phone-reachable public
link, use `./start_demo.sh` instead (see above).

## Build status (see PLAN.md for the order)

1. ✅ Margaret's full visit flow with the verifier loop
2. ✅ Agent builder (real Antigravity + gemini-4-argon, tested against the
   synthetic 2,500-patient panel, persists across restarts, live progress
   from real step events)
3. ✅ Results batch (10 synthetic cases x 3 doc types x 3 methods,
   concurrent, with a real results table + bar chart)
4. ✅ Practice setup and booking page, including adaptive intake
   questions, scheduling, simulated payment, ngrok-aware QR code, and a
   Reset demo button

All phases complete. Pushed to GitHub at
https://github.com/munozmed2017-max/solo (public).
