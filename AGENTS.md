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
- `verifier` **flags risks, it does not block** the pipeline. It always
  runs last among the drafting steps so it can review the prescription and
  prior-auth drafts too.
- `agent_builder` does **not** call `client.agents.create()` in v1. It
  drafts a new prompt + model/thinking_level recommendation as text; a
  human copies it into a new `prompts/*.md` file and a new
  `app.models.ROLE_MODELS` entry by hand.

## Pipeline order (`app/orchestrator.py`)

`intake -> scribe -> prescription -> prior_auth -> verifier -> emails`.
Prescription comes before prior_auth deliberately: prior-auth needs a
specific medication to check against the formulary, which doesn't exist
until the prescription step has drafted one.

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
