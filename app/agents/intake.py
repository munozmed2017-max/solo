ROLE = "intake"
THINKING_LEVEL = "low"


def build_input(case: dict) -> str:
    patient = case["patient"]
    return (
        f"Patient: {patient.get('name')} (DOB {patient.get('dob')})\n"
        f"Known conditions: {', '.join(patient.get('conditions', [])) or 'none on file'}\n"
        f"Current meds: {', '.join(patient.get('meds', [])) or 'none on file'}\n"
        f"Reason for visit: {case['reason']}\n"
        f"Raw visit notes: {case['notes']}\n"
    )
