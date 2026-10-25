ROLE = "emails"
THINKING_LEVEL = "low"


def build_input(visit: dict) -> str:
    scribe_note = visit["documents"].get("scribe", {}).get("output", "")
    prescription = visit["documents"].get("prescription", {}).get("output", "")
    return (
        f"Clinical note:\n{scribe_note}\n\n"
        f"Prescription draft:\n{prescription}\n"
    )
