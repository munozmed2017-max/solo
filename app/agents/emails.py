from app.agents.base import load_prompt, step_output
from app.models import call_model

ROLE = "emails"
THINKING_LEVEL = "low"


def run(case: dict) -> str:
    input_text = (
        f"Clinical note:\n{step_output(case, 'scribe')}\n\n"
        f"Prescription draft:\n{step_output(case, 'prescription')}\n"
    )
    interaction = call_model(
        ROLE,
        input_text,
        thinking_level=THINKING_LEVEL,
        system_instruction=load_prompt(ROLE),
    )
    return interaction.output_text
