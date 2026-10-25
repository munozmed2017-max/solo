from app.agents.base import load_prompt
from app.models import call_model

ROLE = "intake"
THINKING_LEVEL = "low"


def run(case: dict) -> str:
    patient = case["patient"]
    input_text = (
        f"Patient: {patient.get('name')} (DOB {patient.get('dob')})\n"
        f"Known conditions: {', '.join(patient.get('conditions', [])) or 'none on file'}\n"
        f"Current meds: {', '.join(patient.get('meds', [])) or 'none on file'}\n"
        f"Reason for visit: {case['reason']}\n"
        f"Raw visit notes: {case['notes']}\n"
    )
    interaction = call_model(
        ROLE,
        input_text,
        thinking_level=THINKING_LEVEL,
        system_instruction=load_prompt(ROLE),
    )
    return interaction.output_text
