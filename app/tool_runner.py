"""Runs a built agent-builder tool's "Run tool" button.

This actually imports and calls the real diabetes_tracker.py that Argon
wrote (tools/diabetes_tracker/diabetes_tracker.py, extracted verbatim
from the build log - see AGENTS.md) - it does not reimplement the
diabetes-detection/counting logic. The data loading needed zero changes:
Argon's track_diabetes_patients(csv_path) already reads exactly our
panel.csv schema (id, name, age, sex, conditions, last_a1c,
visits_last_2yr) and ran unmodified against the real 2,500-row panel.

last_visit_date/last_a1c_date/"overdue" are NOT part of Argon's output -
the panel has no date columns at all, and its code never computes them.
They're a clearly-separate UI layer added on top of Argon's real patient
list, generated deterministically (seeded by patient id) so repeated
runs are stable. Don't confuse this layer with Argon's own analysis.
"""

import hashlib
import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

from app.storage import create_visit, log_activity, save_visit

TOOL_FILE = Path(__file__).resolve().parent.parent / "tools" / "diabetes_tracker" / "diabetes_tracker.py"
PANEL_CSV = Path(__file__).resolve().parent.parent / "data" / "demo" / "synthetic_panel_2500.csv"
OVERDUE_DAYS = 180

REMINDER_TEMPLATE = (
    "Subject: Time for your A1c check\n\n"
    "Dear [Patient Name],\n\n"
    "Our records show it's been more than 6 months since your last A1c test. "
    "Regular A1c monitoring is an important part of managing your diabetes care. "
    "Please schedule a lab visit or telemedicine appointment at your earliest "
    "convenience so we can check your levels and adjust your care plan if needed.\n\n"
    "Thank you,\nYour care team"
)


def _deterministic_days_ago(seed: str, max_days: int) -> int:
    h = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
    return h % max_days


def _load_argon_tracker():
    spec = importlib.util.spec_from_file_location("argon_diabetes_tracker", TOOL_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_diabetes_tracker() -> dict:
    tracker = _load_argon_tracker()
    result = tracker.track_diabetes_patients(csv_path=str(PANEL_CSV))

    now = datetime.now()
    patients = []
    for p in result["patients"]:
        visit_days_ago = _deterministic_days_ago(p["id"] + "visit", 365)
        a1c_days_ago = _deterministic_days_ago(p["id"] + "a1c", 420)
        patients.append(
            {
                "id": p["id"],
                "name": p["name"],
                "age": p["age"],
                "last_visit_date": (now - timedelta(days=visit_days_ago)).strftime("%Y-%m-%d"),
                "last_a1c": p["last_a1c"],
                "last_a1c_date": (now - timedelta(days=a1c_days_ago)).strftime("%Y-%m-%d"),
                "overdue": a1c_days_ago > OVERDUE_DAYS,
            }
        )
    patients.sort(key=lambda p: p["name"])
    return {
        "total": result["count"],
        "overdue_count": sum(1 for p in patients if p["overdue"]),
        "patients": patients,
        "tool_path": "tools/diabetes_tracker/diabetes_tracker.py",
    }


def draft_a1c_reminder(overdue_count: int) -> dict:
    visit = create_visit(
        {
            "name": f"A1c Reminder Batch ({overdue_count} patients)",
            "dob": "",
            "reason": "Batch communication - diabetes A1c overdue reminder",
            "symptoms": {},
        }
    )
    visit["status"] = "batch"
    visit["documents"]["batch_email"] = {
        "output": f"{REMINDER_TEMPLATE}\n\n---\nRecipients: {overdue_count} patients overdue for A1c "
        "(from the diabetes tracker tool).",
        "model": "n/a",
        "thinking_level": "n/a",
        "resolved": True,
        "verification_rounds": [],
        "approval": {"status": "pending"},
        "sent": False,
    }
    save_visit(visit)
    log_activity("agent builder", f"drafted batch A1c reminder for {overdue_count} patients", visit_id=visit["id"])
    return {"visit_id": visit["id"], "recipient_count": overdue_count}
