ROLE = "scribe"
THINKING_LEVEL = "medium"


def build_input(visit: dict) -> str:
    return (
        f"Intake summary:\n{visit.get('intake_summary') or ''}\n\n"
        f"Visit transcript (physician-provided):\n{visit.get('transcript', '')}\n\n"
        f"Physician's plan:\n{visit.get('physician_plan', '')}\n"
    )
