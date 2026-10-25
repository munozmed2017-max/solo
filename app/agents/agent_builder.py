from app.agents.base import load_prompt
from app.models import LEAD, call_antigravity

ROLE = "agent_builder"


def run(description: str) -> dict:
    """Actually build and test a new back-office tool via a real Antigravity
    managed agent run (gemini-4-argon underneath), not a mocked draft.

    Returns status/output plus the sandbox environment_id and
    interaction_id so a follow-up call could continue the same sandbox
    (e.g. to pull files back) - that follow-up isn't wired up in this UI
    yet, see AGENTS.md.
    """
    instruction = (
        f"{load_prompt(ROLE)}\n\n"
        f"New back-office task to build and test:\n{description}\n"
    )
    interaction = call_antigravity(instruction, model=LEAD)
    return {
        "status": interaction.status,
        "output": interaction.output_text,
        "environment_id": interaction.environment_id,
        "interaction_id": interaction.id,
    }
