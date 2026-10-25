from app.agents.base import patient_record_block, physician_block

ROLE = "prior_auth"
THINKING_LEVEL = "medium"


def build_input(visit: dict) -> str:
    scribe_note = visit["documents"].get("scribe", {}).get("output", "")
    prescription = visit["documents"].get("prescription", {}).get("output", "")
    patient = visit["patient"]
    return (
        f"{patient_record_block(visit)}\n"
        f"{physician_block()}\n"
        f"Insurer: {patient.get('insurer') or 'unknown insurer'}\n"
        f"Clinical note:\n{scribe_note}\n\n"
        f"Prescription draft:\n{prescription}\n"
    )
