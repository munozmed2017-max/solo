ROLE = "intake"
THINKING_LEVEL = "low"


def build_input(visit: dict) -> str:
    patient = visit["patient"]
    booking = visit["booking"]
    symptoms = booking.get("symptoms", {})
    symptoms_text = "\n".join(f"- {k}: {v}" for k, v in symptoms.items()) or "none recorded"
    return (
        f"Patient: {patient.get('name')} (DOB {patient.get('dob')})\n"
        f"Known conditions: {', '.join(patient.get('conditions', [])) or 'none on file'}\n"
        f"Current meds: {', '.join(patient.get('meds', [])) or 'none on file'}\n"
        f"Reason for visit: {booking.get('reason', '')}\n"
        f"Symptom screening answers:\n{symptoms_text}\n"
    )
