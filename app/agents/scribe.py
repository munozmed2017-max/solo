from app.agents.base import patient_record_block, physician_block

ROLE = "scribe"
THINKING_LEVEL = "medium"


def build_input(visit: dict) -> str:
    return (
        f"{patient_record_block(visit)}\n"
        f"{physician_block()}\n"
        f"Intake summary:\n{visit.get('intake_summary') or ''}\n\n"
        f"Visit transcript (physician-provided, verbatim):\n{visit.get('transcript', '')}\n\n"
        "Physician's plan (verbatim - the ONLY source for what goes in the "
        f"note's Plan section):\n{visit.get('physician_plan', '')}\n"
    )
