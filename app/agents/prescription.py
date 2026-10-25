from app.agents.base import step_output
from tools.clinical import check_drug_interactions

ROLE = "prescription"
THINKING_LEVEL = "medium"


def build_input(case: dict) -> str:
    patient = case["patient"]
    interaction_check = check_drug_interactions(patient.get("meds", []))
    return (
        f"Clinical note:\n{step_output(case, 'scribe')}\n\n"
        f"Drug interaction check against current meds {patient.get('meds', [])}:\n"
        f"{interaction_check}\n"
    )
