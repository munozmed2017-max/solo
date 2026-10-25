# Solo

**Practice solo. Never alone.**

Solo is a web app for a solo physician running their own telemedicine
practice, with the back office — intake, scheduling, payment, clinical
notes, prescriptions, prior authorizations, and patient messages — run
by a team of Gemini agents instead of staff.

## Problem Statement One

> **Million Token Engineering.** Gemini 4 Argon is SOTA on codebase
> understanding, which measures long-horizon software engineering. With
> up to 1M continuous output tokens in a single response, Argon makes it
> possible to build systems that work across hundreds of files, keep
> interfaces consistent as they change, and grind tedious tasks where
> other models' accuracy drops off. The work teams put off for years
> (legacy migrations, language translations, framework upgrades) is
> exactly where that scale matters. Pick something that has before
> seemed as a monumental task, do it, and measure your improvement over
> a baseline.

**Our framing:** the monumental task is running a medical practice's
entire back office — intake, scheduling, payment, notes, prescriptions,
prior authorizations, patient messages — without staff, *and* building
new practice software on demand instead of waiting on a vendor. Both
halves lean on exactly the long-horizon capability the statement is
about: a consistent multi-agent pipeline that holds its own rules
(never invent an instruction the physician didn't give, always ground
every document in the same patient record) across many files and many
calls, and a managed coding agent that writes, tests, and runs new
tools against real data without a human in the loop.

**We measured it, not just built it.** Three ways to generate the same
three document types (clinical note, prescription, prior authorization)
across 10 synthetic cases:

| Method | Coverage | Avg errors/doc | Errors caught | Avg time/doc | Total tokens |
|---|---|---|---|---|---|
| Flash baseline (generic prompt, no verifier) | 100% | 4.63 | 0 | 6.8s | 36,621 |
| Argon agents (specialized prompts, no verifier) | 100% | 0.9 | 0 | 12.1s | 49,588 |
| Argon agents + verifier (blocking, up to 3 rounds) | 100% | 0.8 | 24 | 34.6s | 64,817 |

Argon agents made about **5.1x fewer errors** than the Flash baseline
just from specialized, grounded prompts — before the verifier ever runs.
The verifier then caught all 24 of the errors it found in round-1 drafts
before they ever reached the physician. Errors are measured the same way
for every method: baseline and Argon-agents-only have no internal
verifier, so each of their final documents gets one independent grading
pass from the same verifier the third method uses internally — nobody
grades their own homework. Cost is reported as total tokens, not a
dollar figure, since there's no verified public pricing to cite for
these model names.

The agent builder is the other half of the pitch: given "find all my
patients with diabetes and track their visits and A1c," a real
Antigravity managed agent running Gemini 4 Argon wrote a Python tool,
wrote a test against hand-built fake rows, ran the test, then ran the
real tool against a synthetic 2,500-patient panel — and its reported
count matched the panel's independently-computed true count exactly:
**465 = 465**. No human wrote that tool; Argon did, end to end, and the
match proves it got the right answer on real (if synthetic) data, not
just plausible-sounding code.

## What was built

1. **Visits** — a patient books (name, DOB, reason, adaptive follow-up
   questions, a time slot, simulated payment) and the visit appears
   automatically with intake already run. The physician reviews a
   transcript + plan, clicks Approve, and the pipeline drafts a clinical
   note, prescription (labeled SIMULATED FAX), and patient summary
   email — each independently verified.
2. **Approval queue** — every drafted document, with Approve / Edit /
   Reject. Sending a document without an approval record is blocked in
   code (`app/storage.py::mark_document_sent`), not just hidden in the
   UI — the route returns a 403 if you try.
3. **Activity log** — every agent, physician, and system action, with
   timestamps, including the scheduling agent and billing agent.
4. **Agent builder** — physicians describe a new back-office tool in
   plain language; a real Antigravity-managed Gemini 4 Argon agent
   writes it, tests it, and runs it against a synthetic patient panel.
   Live progress is driven by real step events from the agent, not a
   fake spinner. Built tools persist under "My tools."
5. **Results** — the batch comparison above, re-runnable on demand, with
   a bar chart and a plain-language summary sentence computed from the
   live numbers.
6. **Practice setup** — name, physician, hours, fee, a QR code to the
   booking page (ngrok-aware — always points at the live public tunnel
   when one is running), and simulated practice earnings.
7. **Booking page** — public, no login, banner: *"Use made-up
   information only."* Adaptive intake questions, scheduling, and a
   no-card simulated checkout.

## Agents and models

| Agent | Role | Model | Why |
|---|---|---|---|
| `orchestrator` | sequences the visit pipeline | `gemini-4-argon` | needs to hold the whole case consistently |
| `scribe` | clinical note (SOAP) | `gemini-4-argon` | clinical synthesis, strict grounding rules |
| `prior_auth` | prior-authorization letters | `gemini-4-argon` | same strict grounding, used in the Results benchmark |
| `verifier` | independent sentence-level check | `gemini-4-argon`, `thinking_level=high` | the one agent that has to catch the others' mistakes |
| `agent_builder` | writes/tests/runs new tools | `gemini-4-argon` via the Antigravity managed agent | real code generation and execution |
| `intake` | intake summary + adaptive follow-up questions | `gemini-3.8-flash`, `thinking_level=low` | fast, high-volume, low-stakes |
| `prescription` | prescription orders | `gemini-3.8-flash` | drafts only, never submitted anywhere |
| `emails` | patient after-visit summary | `gemini-3.8-flash` | fast, grounded strictly in the physician's actual words |
| `baseline` | the Flash baseline in the Results benchmark | `gemini-3.8-flash` | the thing we're measuring improvement over |

Every model call goes through one function
(`app/models.py::call_model`), and only `thinking_level` is ever set —
never `temperature`, `top_p`, `top_k`, or `thinking_budget`.

## The verifier loop

The verifier is **blocking**, not advisory. For every drafted document:

1. The agent drafts it.
2. An **independent** `gemini-4-argon` call checks it sentence by
   sentence against ground truth (the patient record, the physician's
   actual plan and transcript, and the physician's name) and returns
   structured pass/fail with a reason per failing sentence.
3. A failure sends the exact failing sentences back to the *same* agent
   to rewrite.
4. Repeat, **up to 3 rounds**. If round 3 still fails, the visit is
   flagged `needs_manual_review` instead of looping forever.

Every round — draft text, verdict, failing sentences, reasons — is kept
and shown in the UI, not discarded. For prescriptions and patient
emails, the verifier enforces a stricter rule: every sentence must trace
to something the physician actually wrote or said, no added advice or
precautions, however reasonable they'd sound. A demo switch,
`DEMO_PLANTED_ERROR`, inserts a stale lab value into Margaret's first
scribe draft so the loop has a real error to catch on camera — in
testing, it was caught and rewritten correctly every time.

## Synthetic data

Every patient, lab value, case, and the 2,500-row panel used by the
agent builder is synthetic. Margaret Smith and Jhonatan are fictional
demo patients; the booking page's banner tells real users the same
thing: "Use made-up information only." Nothing in this repository is
real patient data.

## Simulated, not real

- **Prescriptions** are labeled **SIMULATED FAX** in the UI. Nothing is
  ever transmitted to a real pharmacy or payer — these are drafts for
  the physician to review and sign.
- **Payment** is a simulated checkout: no card fields, clicking "Pay"
  just marks the visit paid in the app's own records.
- Drug-interaction checks, formulary lookups, and the practice "hours"
  parser are simple/stubbed where a real integration would normally go.

## How to run

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

Put your Gemini API key in `.env` at the repo root:

```
GEMINI_API_KEY=your-key-here
```

Then either:

```bash
./.venv/bin/uvicorn app.main:app --reload --port 8000
```
and open http://localhost:8000, **or**, to also get a phone-reachable
public link via ngrok (requires your own free ngrok account and
authtoken, see `AGENTS.md`):

```bash
./start_demo.sh
```

See `AGENTS.md` for implementation notes, known quirks, and what's
mocked vs. real. See `PLAN.md` for the original product spec.
