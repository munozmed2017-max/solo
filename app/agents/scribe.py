from app.agents.base import load_prompt, step_output
from app.models import call_model

ROLE = "scribe"
THINKING_LEVEL = "medium"


def run(case: dict) -> str:
    input_text = (
        f"Intake summary:\n{step_output(case, 'intake')}\n\n"
        f"Raw visit notes:\n{case['notes']}\n"
    )
    interaction = call_model(
        ROLE,
        input_text,
        thinking_level=THINKING_LEVEL,
        system_instruction=load_prompt(ROLE),
    )
    return interaction.output_text
