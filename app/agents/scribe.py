from app.agents.base import step_output

ROLE = "scribe"
THINKING_LEVEL = "medium"


def build_input(case: dict) -> str:
    return (
        f"Intake summary:\n{step_output(case, 'intake')}\n\n"
        f"Raw visit notes:\n{case['notes']}\n"
    )
