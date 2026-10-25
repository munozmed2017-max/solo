# AGENTS.md

Setup quirks and conventions for this repo. Read this before changing
`app/models.py` or adding a new agent.

## Environment

- Python 3.11+ (built/tested on 3.15, `./.venv`). Dependencies in
  `requirements.txt`, pinned to `google-genai>=2.30.1` (the version this
  skill/project was built against; the user's original ask said 2.3.0+,
  but that line is long EOL — use the pinned floor).
- `GEMINI_API_KEY` lives in `.env` at the repo root (gitignored). Loaded via
  `python-dotenv` in `app/models.py`. Never commit `.env`.

## Model roster (`app/models.py`)

- `LEAD = "gemini-4-argon"` — orchestrator, scribe, prior_auth, verifier,
  agent_builder.
- `FAST = "gemini-3.8-flash"` — intake, prescription, emails, and the
  baseline for any unlisted role.
- Every call goes through `call_model(role, input_text, thinking_level, ...)`
  in `app/models.py`. **Never pass `temperature`, `top_p`, `top_k`, or
  `thinking_budget`** — only `thinking_level` (one of `minimal`, `low`,
  `medium`, `high`), set per call inside `generation_config`.
- HTTP timeout is set on the client via
  `genai.Client(http_options={"timeout": 1_200_000})` (ms) = 20 minutes.
  This is a client-transport option, not an Interactions API parameter —
  if a future `google-genai` release renames/removes it, check the
  installed SDK's `HttpOptions` type.

## Data retention note (read before pointing this at real patients)

By default, Gemini Interactions are **stored server-side** (`store=True`
implicitly) — up to 55 days on a paid tier, 1 day on free. This project
currently does **not** set `store=False`, on the assumption this is a
prototype using synthetic/demo patients (`data/demo/panel_seed.json`), not
real PHI. If you start using this with real patients, set `store=False` in
`app/models.py::call_model` — but note that disables
`previous_interaction_id` and `background=True`, so each agent call is
already stateless in this codebase (no conversation chaining between
agents), so flipping that switch is low-risk here.

## Safety/scope boundaries baked into the prompts

- `prior_auth` and `prescription` agents only **draft text for the
  physician to review and sign** — nothing is submitted to a pharmacy or
  payer. There is no e-prescribing or payer integration in this codebase.

## Verification loop (`app/verify.py`) — blocking, not advisory

The verifier **blocks and loops**, it does not just flag risks. For every
drafting step (intake, scribe, prescription, prior_auth, emails):

1. The agent drafts the document.
2. `verifier.check()` (gemini-4-argon, `thinking_level=high`, forced JSON
   via `response_format`) checks it sentence-by-sentence against ground
   truth (patient chart + raw notes + whatever upstream context that
   agent was given) and returns `{passed, failures: [{sentence, reason}]}`.
3. If `passed` is false, the *same* document, plus the exact failing
   sentences and reasons, goes back to the *same* agent to rewrite
   (`app.verify._revise`).
4. Repeat from step 2. **Up to 3 rounds total.** If round 3 still fails,
   the loop stops and the step is marked `resolved: false` — the case
   gets `needs_manual_review: true` and the UI flags it so the physician
   reviews it by hand instead of the loop running forever.

Every round (draft text + verifier verdict) is kept on
`step["verification_rounds"]` in the case JSON and shown in the UI under
each step's "Verification log" — nothing from the loop is discarded, even
on a run that never resolves.

This roughly tripled real API calls and wall-clock time per case run
compared to a single flag-only verifier pass (worst case: 5 documents ×
up to 3 drafts + 3 verifies each). That's the deliberate tradeoff for
having the verifier actually gate output instead of just annotating it.

## Agent builder (`app/agents/agent_builder.py`) — real, not mocked

`agent_builder` calls the **real Antigravity managed agent**
(`antigravity-preview-09-2026`) with `agent_config={"type": "antigravity",
"model": "gemini-4-argon"}` and `environment="remote"` — a real sandboxed
Linux VM that writes code, executes it, and iterates until its own test
passes, via `app.models.call_antigravity`. This is a real paid API call
(Google's docs cite roughly $0.30–$3+ per run depending on task size) and
can take one to a few minutes. It is **not** wired into the automated
case pipeline — it's a standalone tool invoked from the UI/`/api/agent-
builder`, for building new tools, not for running cases.

Not yet wired up (explicit scope cut, not a mock): pulling the actual
files (`tool.py`, `test_*.py`) back out of the sandbox via the Files API
download endpoint. Right now you get the agent's narrated final report
(which includes the code inline), not a downloaded file. The
`environment_id`/`interaction_id` returned from the call are enough to
continue that same sandbox in a follow-up call if you want to add that
later.

## What's still mocked in this project

- **`tools/clinical.py`** — `check_drug_interactions`,
  `check_insurance_formulary`, `schedule_followup` are stubs with
  fake/deterministic-hash data, not real integrations (no real pharmacy,
  formulary, or payer API, no real calendar). Agents call them as plain
  Python functions, not as Gemini function-calling tools.
- **`data/demo/panel_seed.json`** — synthetic patients, not real ones.
- **Prescription/prior-auth submission** — drafts only, nothing is ever
  actually sent to a pharmacy or payer (this is a deliberate safety
  boundary, not a cut corner — see above).
- **Antigravity file retrieval** — see above; the sandbox really runs,
  but its files aren't auto-downloaded yet.

`agent_builder` is the only thing that was mocked and has now been made
real per explicit instruction. Everything else above is an intentional
v1 scope boundary, not something pretending to be real.

## Pipeline order (`app/orchestrator.py`)

`intake -> scribe -> prescription -> prior_auth -> emails`, each wrapped
in the verify-and-revise loop above. Prescription comes before prior_auth
deliberately: prior-auth needs a specific medication to check against the
formulary, which doesn't exist until the prescription step has drafted
one.

## Storage (`app/storage.py`)

Flat JSON files, no database:
- `data/panel/panel.json` — patient panel, auto-seeded from
  `data/demo/panel_seed.json` on first run if it doesn't exist yet.
- `data/cases/<case_id>.json` — one file per case, gitignored (treat as
  potentially sensitive even with demo data, since this is where real
  patient data would land if you start using live data).
- `runs/<case_id>_<run_id>.json` — one audit log per pipeline run,
  gitignored.

## Mock tools (`tools/clinical.py`)

`check_drug_interactions`, `check_insurance_formulary`, and
`schedule_followup` are stubs with fake/deterministic-hash data — not real
integrations. Agents call them directly as plain Python functions (not
wired as Gemini function-calling tools). Swap the function bodies for real
API calls later; keep the return shape the same so agent prompts don't
need to change.

## Running it

```
./.venv/bin/uvicorn app.main:app --reload --port 8000
```

Then open http://localhost:8000 in a browser. `/test-argon` is a plain
GET endpoint for a quick sanity check outside the UI too.
