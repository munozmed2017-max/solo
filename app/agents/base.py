from pathlib import Path

from app.storage import get_practice

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text()


def patient_record_block(visit: dict) -> str:
    """Every agent and the verifier get this - the one source of patient
    facts, so no agent is ever guessing a name, DOB, or pharmacy."""
    patient = visit["patient"]
    lines = [
        f"Full name: {patient.get('name') or 'unknown'}",
        f"Date of birth: {patient.get('dob') or 'unknown'}",
        f"Conditions: {', '.join(patient.get('conditions', [])) or 'none on file'}",
        f"Current medications: {', '.join(patient.get('meds', [])) or 'none on file'}",
        f"Labs on file: {patient.get('labs', [])}",
        f"Vitals on file: {patient.get('vitals', {})}",
        f"Pharmacy on file: {patient.get('pharmacy') or 'none on file'}",
    ]
    return "Patient record (ground truth - state these facts exactly, never guess or omit them):\n" + "\n".join(lines) + "\n"


def physician_block() -> str:
    practice = get_practice()
    return f"Signing physician: {practice.get('physician_name') or 'the physician'}\n"
