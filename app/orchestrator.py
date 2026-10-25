"""Fixed sequential pipeline per case.

Order matters clinically: prescription must exist before prior-auth can
reference a specific medication. The verifier is no longer a separate
final pipeline stage - it's embedded in every drafting step via
app.verify.run_with_verification, which blocks and loops revisions
(see app/verify.py) instead of just flagging risks at the end.
"""

from app.agents import emails, intake, prescription, prior_auth, scribe
from app.models import model_for_role
from app.storage import save_case, save_run_log
from app.verify import run_with_verification

PIPELINE = [intake, scribe, prescription, prior_auth, emails]


def _patient_chart(case: dict) -> str:
    patient = case["patient"]
    return (
        "Patient chart on file (ground truth):\n"
        f"Conditions: {', '.join(patient.get('conditions', [])) or 'none on file'}\n"
        f"Current meds: {', '.join(patient.get('meds', [])) or 'none on file'}\n"
        f"Original raw visit notes for this encounter: {case['notes']}\n"
    )


def run_pipeline(case: dict) -> dict:
    run_log = {"case_id": case["id"], "steps": []}
    done = {s["agent"] for s in case["steps"]}
    patient_chart = _patient_chart(case)

    for module in PIPELINE:
        if module.ROLE in done:
            continue
        result = run_with_verification(module, case, patient_chart)
        step = {
            "agent": module.ROLE,
            "model": model_for_role(module.ROLE),
            "thinking_level": module.THINKING_LEVEL,
            "output": result["output"],
            "resolved": result["resolved"],
            "verification_rounds": result["rounds"],
            "approved": None,
        }
        case["steps"].append(step)
        run_log["steps"].append(step)
        save_case(case)

    case["status"] = "reviewed" if len(case["steps"]) == len(PIPELINE) else "in_progress"
    case["needs_manual_review"] = any(not s.get("resolved", True) for s in case["steps"])
    save_case(case)
    save_run_log(case["id"], run_log)
    return case
