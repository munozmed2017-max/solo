from app.agents.base import load_prompt
from app.models import call_model

ROLE = "agent_builder"
THINKING_LEVEL = "low"


def run(description: str) -> str:
    interaction = call_model(
        ROLE,
        f"New back-office task to design an agent for:\n{description}\n",
        thinking_level=THINKING_LEVEL,
        system_instruction=load_prompt(ROLE),
    )
    return interaction.output_text
