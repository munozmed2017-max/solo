from tools.clinical import check_drug_interactions

ROLE = "prescription"
THINKING_LEVEL = "medium"


def build_input(visit: dict) -> str:
    patient = visit["patient"]
    scribe_note = visit["documents"].get("scribe", {}).get("output", "")
    interaction_check = check_drug_interactions(patient.get("meds", []))
    return (
        f"Clinical note:\n{scribe_note}\n\n"
        f"Drug interaction check against current meds {patient.get('meds', [])}:\n"
        f"{interaction_check}\n"
    )
