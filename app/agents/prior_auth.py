from app.agents.base import load_prompt, step_output
from app.models import call_model
from tools.clinical import check_insurance_formulary

ROLE = "prior_auth"
THINKING_LEVEL = "medium"


def run(case: dict) -> str:
    patient = case["patient"]
    prescription = step_output(case, "prescription")
    formulary_check = check_insurance_formulary(
        patient.get("insurer", "unknown insurer"), prescription or case["reason"]
    )
    input_text = (
        f"Clinical note:\n{step_output(case, 'scribe')}\n\n"
        f"Prescription draft:\n{prescription}\n\n"
        f"Insurer: {patient.get('insurer', 'unknown insurer')}\n"
        f"Formulary/coverage lookup result:\n{formulary_check}\n"
    )
    interaction = call_model(
        ROLE,
        input_text,
        thinking_level=THINKING_LEVEL,
        system_instruction=load_prompt(ROLE),
    )
    return interaction.output_text
