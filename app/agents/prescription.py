from app.agents.base import load_prompt, step_output
from app.models import call_model
from tools.clinical import check_drug_interactions

ROLE = "prescription"
THINKING_LEVEL = "medium"


def run(case: dict) -> str:
    patient = case["patient"]
    interaction_check = check_drug_interactions(patient.get("meds", []))
    input_text = (
        f"Clinical note:\n{step_output(case, 'scribe')}\n\n"
        f"Drug interaction check against current meds {patient.get('meds', [])}:\n"
        f"{interaction_check}\n"
    )
    interaction = call_model(
        ROLE,
        input_text,
        thinking_level=THINKING_LEVEL,
        system_instruction=load_prompt(ROLE),
    )
    return interaction.output_text
