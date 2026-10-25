from app.agents.base import patient_record_block, physician_block

ROLE = "prescription"
THINKING_LEVEL = "medium"


def build_input(visit: dict) -> str:
    scribe_note = visit["documents"].get("scribe", {}).get("output", "")
    return (
        f"{patient_record_block(visit)}\n"
        f"{physician_block()}\n"
        f"Clinical note:\n{scribe_note}\n"
    )
