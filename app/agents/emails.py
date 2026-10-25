from app.agents.base import patient_record_block, physician_block

ROLE = "emails"
THINKING_LEVEL = "low"


def build_input(visit: dict) -> str:
    scribe_note = visit["documents"].get("scribe", {}).get("output", "")
    prescription = visit["documents"].get("prescription", {}).get("output", "")
    return (
        f"{patient_record_block(visit)}\n"
        f"{physician_block()}\n"
        f"Clinical note:\n{scribe_note}\n\n"
        f"Prescription draft:\n{prescription}\n\n"
        f"Visit transcript (physician-provided, verbatim):\n{visit.get('transcript', '')}\n\n"
        "Physician's plan (verbatim - the ONLY source for new instructions "
        f"to the patient):\n{visit.get('physician_plan', '')}\n"
    )
