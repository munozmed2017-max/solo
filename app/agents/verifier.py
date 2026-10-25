from app.agents.base import load_prompt, step_output
from app.models import call_model

ROLE = "verifier"
THINKING_LEVEL = "high"


def run(case: dict) -> str:
    patient = case["patient"]
    input_text = (
        f"Patient chart on file (treat as ground truth, not a hallucination, "
        f"when it shows up in other agents' outputs):\n"
        f"Conditions: {', '.join(patient.get('conditions', [])) or 'none on file'}\n"
        f"Current meds: {', '.join(patient.get('meds', [])) or 'none on file'}\n\n"
        f"Original raw notes from this visit:\n{case['notes']}\n\n"
        f"Intake summary:\n{step_output(case, 'intake')}\n\n"
        f"Clinical note:\n{step_output(case, 'scribe')}\n\n"
        f"Prescription draft:\n{step_output(case, 'prescription')}\n\n"
        f"Prior-auth draft:\n{step_output(case, 'prior_auth')}\n"
    )
    interaction = call_model(
        ROLE,
        input_text,
        thinking_level=THINKING_LEVEL,
        system_instruction=load_prompt(ROLE),
    )
    return interaction.output_text
