"""Visit pipeline.

Intake is generated eagerly when a visit is booked - it's reference
material for the physician, not a reviewed/approved document. Scribe,
prescription, and email are generated together when the physician clicks
Approve on the transcript/plan, each gated by the verify-and-revise loop
in app.verify. Nothing is marked sent without a separate human approval
record - see storage.mark_document_sent.
"""

from app.agents import emails, intake as intake_agent, prescription, scribe
from app.agents.base import load_prompt, patient_record_block, physician_block
from app.models import call_model, model_for_role
from app.storage import get_flags, log_activity, save_run_log, save_visit
from app.verify import run_with_verification

DOCUMENT_PIPELINE = [scribe, prescription, emails]

# DEMO_PLANTED_ERROR: see PLAN.md. Inserted into Margaret's first scribe
# draft only, so the verifier has something real to catch and reject.
PLANTED_ERROR_TEXT = "Potassium is elevated at 5.4."
PLANTED_ERROR_PATIENT = "margaret smith"


def _patient_chart(visit: dict) -> str:
    """Ground truth handed to the verifier for every document type. Includes
    the physician's plan and transcript verbatim, not just the chart, so the
    strict no-invented-instructions rule has something concrete to check
    against regardless of which document is being reviewed."""
    booking = visit["booking"]
    return (
        f"{patient_record_block(visit)}\n"
        f"{physician_block()}\n"
        f"Reason given at booking: {booking.get('reason', '')}\n"
        f"Symptom screening at booking: {booking.get('symptoms', {})}\n"
        f"Visit transcript (physician-provided, verbatim):\n{visit.get('transcript', '')}\n\n"
        "Physician's plan (verbatim - the ONLY source for new instructions "
        f"to the patient):\n{visit.get('physician_plan', '')}\n"
    )


def generate_intake(visit: dict) -> dict:
    interaction = call_model(
        intake_agent.ROLE,
        intake_agent.build_input(visit),
        thinking_level=intake_agent.THINKING_LEVEL,
        system_instruction=load_prompt(intake_agent.ROLE),
    )
    visit["intake_summary"] = interaction.output_text
    visit["status"] = "intake_ready"
    save_visit(visit)
    log_activity("intake agent", "generated intake summary", visit_id=visit["id"])
    return visit


def approve_visit(visit: dict) -> dict:
    """Physician approved the transcript/plan - run the 3-document pipeline."""
    patient_chart = _patient_chart(visit)
    flags = get_flags()
    is_planted_error_patient = visit["patient"].get("name", "").strip().lower() == PLANTED_ERROR_PATIENT
    run_log = {"visit_id": visit["id"], "documents": []}

    for module in DOCUMENT_PIPELINE:
        inject = None
        if module.ROLE == "scribe" and is_planted_error_patient and flags.get("DEMO_PLANTED_ERROR"):
            inject = PLANTED_ERROR_TEXT
            log_activity(
                "demo switch",
                "DEMO_PLANTED_ERROR is on - injecting a planted error into the scribe draft",
                visit_id=visit["id"],
            )

        log_activity(f"{module.ROLE} agent", "drafting document", visit_id=visit["id"])
        result = run_with_verification(module, visit, patient_chart, inject_error_text=inject)

        for r in result["rounds"]:
            if r["passed"]:
                msg = f"round {r['round']} on {module.ROLE}: passed"
            else:
                msg = f"round {r['round']} on {module.ROLE}: rejected {len(r['failures'])} sentence(s)"
            log_activity("verifier agent", msg, visit_id=visit["id"])

        visit["documents"][module.ROLE] = {
            "output": result["output"],
            "model": model_for_role(module.ROLE),
            "thinking_level": module.THINKING_LEVEL,
            "resolved": result["resolved"],
            "verification_rounds": result["rounds"],
            "approval": {"status": "pending"},
            "sent": False,
        }
        save_visit(visit)
        run_log["documents"].append({"doc_type": module.ROLE, **result})

    visit["status"] = "awaiting_approval"
    visit["needs_manual_review"] = any(
        not d.get("resolved", True) for d in visit["documents"].values()
    )
    save_visit(visit)
    save_run_log(visit["id"], run_log)
    log_activity("orchestrator", "pipeline complete, documents awaiting approval", visit_id=visit["id"])
    return visit
