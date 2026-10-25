"""Phase 3: Results batch.

10 synthetic cases x 3 document types (note, prescription, prior_auth) x
3 methods (Flash baseline, Argon agents, Argon agents + verifier), run
concurrently. Flash baseline and Argon agents (no verifier) are graded
after the fact by one independent verifier.check() pass each, so "errors
found" is measured the same way for every method. Argon agents + verifier
already knows its own error count from its internal rounds - round 1's
failure count is its "errors found" (a fair comparison point: what a
single first draft would have contained), and "errors caught" is how many
of those got fixed by the time the loop stopped.
"""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from app.agents import prescription, prior_auth, scribe, verifier
from app.agents.base import load_prompt
from app.models import call_model
from app.orchestrator import _patient_chart
from app.storage import bump_results_progress, fail_results_run, finish_results_run, start_results_run
from app.verify import run_with_verification

DEMO_DIR = Path(__file__).resolve().parent.parent / "data" / "demo"
CASES_FILE = DEMO_DIR / "results_cases.json"

DOC_ORDER = ["note", "prescription", "prior_auth"]
DOC_MODULES = {"note": scribe, "prescription": prescription, "prior_auth": prior_auth}
ROLE_FOR_DOC = {"note": "scribe", "prescription": "prescription", "prior_auth": "prior_auth"}

METHODS = ["flash_baseline", "argon_agents", "argon_verified"]
METHOD_LABELS = {
    "flash_baseline": "Flash baseline",
    "argon_agents": "Argon agents",
    "argon_verified": "Argon agents + verifier",
}

MAX_WORKERS = 15

_progress_lock = threading.Lock()

BASELINE_PROMPTS = {
    "note": "Write a clinical note for this telemedicine visit based on the information given.",
    "prescription": "Write a prescription based on the clinical note and physician's plan given.",
    "prior_auth": "Write a prior authorization letter to the insurer based on the clinical note and prescription given.",
}


def _load_cases() -> list[dict]:
    return json.loads(CASES_FILE.read_text())


def _case_to_visit(case: dict) -> dict:
    return {
        "patient": case["patient"],
        "booking": {"reason": case["reason"], "symptoms": {}},
        "transcript": case["transcript"],
        "physician_plan": case["physician_plan"],
        "intake_summary": "",
        "documents": {},
    }


def _baseline_input(doc_key: str, visit: dict) -> str:
    patient = visit["patient"]
    parts = [
        f"Patient: {patient.get('name')} (DOB {patient.get('dob')})",
        f"Conditions: {', '.join(patient.get('conditions', []))}",
        f"Meds: {', '.join(patient.get('meds', []))}",
        f"Reason for visit: {visit['booking']['reason']}",
        f"Transcript: {visit['transcript']}",
        f"Physician's plan: {visit['physician_plan']}",
    ]
    if doc_key in ("prescription", "prior_auth"):
        parts.append(f"Clinical note already written: {visit['documents'].get('scribe', {}).get('output', '')}")
    if doc_key == "prior_auth":
        parts.append(f"Prescription already written: {visit['documents'].get('prescription', {}).get('output', '')}")
        parts.append(f"Insurer: {patient.get('insurer')}")
    return "\n".join(parts)


def _usage_tokens(interaction) -> int:
    return getattr(getattr(interaction, "usage", None), "total_tokens", 0) or 0


def _run_baseline_doc(doc_key: str, visit: dict) -> dict:
    t0 = time.time()
    interaction = call_model(
        "baseline", f"{BASELINE_PROMPTS[doc_key]}\n\n{_baseline_input(doc_key, visit)}", thinking_level="low"
    )
    return {"output": interaction.output_text or "", "elapsed": time.time() - t0, "tokens": _usage_tokens(interaction)}


def _run_argon_doc(doc_key: str, visit: dict) -> dict:
    module = DOC_MODULES[doc_key]
    t0 = time.time()
    interaction = call_model(
        module.ROLE,
        module.build_input(visit),
        thinking_level=module.THINKING_LEVEL,
        system_instruction=load_prompt(module.ROLE),
    )
    return {"output": interaction.output_text or "", "elapsed": time.time() - t0, "tokens": _usage_tokens(interaction)}


def _run_argon_verified_doc(doc_key: str, visit: dict, patient_chart: str) -> dict:
    module = DOC_MODULES[doc_key]
    t0 = time.time()
    result = run_with_verification(module, visit, patient_chart)
    elapsed = time.time() - t0
    rounds = result["rounds"]
    round1_failures = len(rounds[0]["failures"]) if rounds else 0
    last_failures = len(rounds[-1]["failures"]) if rounds else 0
    errors_caught = round1_failures if result["resolved"] else max(0, round1_failures - last_failures)
    return {
        "output": result["output"],
        "elapsed": elapsed,
        "tokens": result.get("tokens", 0),
        "errors_found": round1_failures,
        "errors_caught": errors_caught,
        "resolved": result["resolved"],
    }


def _grade(doc_key: str, output: str, patient_chart: str, visit: dict) -> int:
    module = DOC_MODULES[doc_key]
    context = f"{patient_chart}\n\n{module.build_input(visit)}"
    result = verifier.check(module.ROLE, output, context)
    return len(result.failures)


def _run_case_method(case: dict, method: str) -> tuple[str, str, dict]:
    visit = _case_to_visit(case)
    patient_chart = _patient_chart(visit)
    case_result = {}
    for doc_key in DOC_ORDER:
        if method == "flash_baseline":
            r = _run_baseline_doc(doc_key, visit)
            r["errors_found"] = _grade(doc_key, r["output"], patient_chart, visit)
            r["errors_caught"] = 0
        elif method == "argon_agents":
            r = _run_argon_doc(doc_key, visit)
            r["errors_found"] = _grade(doc_key, r["output"], patient_chart, visit)
            r["errors_caught"] = 0
        else:
            r = _run_argon_verified_doc(doc_key, visit, patient_chart)

        visit["documents"][ROLE_FOR_DOC[doc_key]] = {"output": r["output"]}
        case_result[doc_key] = r
        with _progress_lock:
            bump_results_progress()
    return case["id"], method, case_result


def _aggregate(raw: dict) -> list[dict]:
    table = []
    for method in METHODS:
        docs = [r for case_result in raw[method].values() for r in case_result.values()]
        total = len(docs)
        covered = sum(1 for d in docs if d["output"].strip())
        table.append(
            {
                "method": METHOD_LABELS[method],
                "doc_count": total,
                "coverage_pct": round(100 * covered / total, 1) if total else 0.0,
                "avg_errors_per_doc": round(sum(d["errors_found"] for d in docs) / total, 2) if total else 0.0,
                "errors_caught_total": sum(d["errors_caught"] for d in docs),
                "avg_time_per_doc_sec": round(sum(d["elapsed"] for d in docs) / total, 1) if total else 0.0,
                "total_tokens": sum(d.get("tokens", 0) for d in docs),
            }
        )
    return table


def run_batch() -> list[dict]:
    cases = _load_cases()
    total_units = len(cases) * len(METHODS) * len(DOC_ORDER)
    start_results_run(total_units)
    t0 = time.time()

    raw = {m: {} for m in METHODS}
    try:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = [ex.submit(_run_case_method, case, method) for case in cases for method in METHODS]
            for fut in as_completed(futures):
                case_id, method, case_result = fut.result()
                raw[method][case_id] = case_result
    except Exception as e:
        fail_results_run(str(e))
        raise

    table = _aggregate(raw)
    finish_results_run(table, time.time() - t0)
    return table


def start_batch_background() -> None:
    threading.Thread(target=run_batch, daemon=True).start()
