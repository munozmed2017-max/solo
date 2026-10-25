from app.agents.base import step_output
from tools.clinical import check_insurance_formulary

ROLE = "prior_auth"
THINKING_LEVEL = "medium"


def build_input(case: dict) -> str:
    patient = case["patient"]
    prescription = step_output(case, "prescription")
    formulary_check = check_insurance_formulary(
        patient.get("insurer", "unknown insurer"), prescription or case["reason"]
    )
    return (
        f"Clinical note:\n{step_output(case, 'scribe')}\n\n"
        f"Prescription draft:\n{prescription}\n\n"
        f"Insurer: {patient.get('insurer', 'unknown insurer')}\n"
        f"Formulary/coverage lookup result:\n{formulary_check}\n"
    )
