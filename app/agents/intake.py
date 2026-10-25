from app.agents.base import patient_record_block, physician_block

ROLE = "intake"
THINKING_LEVEL = "low"


def build_input(visit: dict) -> str:
    booking = visit["booking"]
    symptoms = booking.get("symptoms", {})
    symptoms_text = "\n".join(f"- {k}: {v}" for k, v in symptoms.items()) or "none recorded"
    return (
        f"{patient_record_block(visit)}\n"
        f"{physician_block()}\n"
        f"Reason for visit: {booking.get('reason', '')}\n"
        f"Symptom screening answers:\n{symptoms_text}\n"
    )
