from app.agents.base import step_output

ROLE = "emails"
THINKING_LEVEL = "low"


def build_input(case: dict) -> str:
    return (
        f"Clinical note:\n{step_output(case, 'scribe')}\n\n"
        f"Prescription draft:\n{step_output(case, 'prescription')}\n"
    )
