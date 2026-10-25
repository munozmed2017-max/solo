"""Runs a built agent-builder tool's logic for the "Run tool" button.

The tool's actual code only exists inside the Antigravity sandbox that
wrote it (never downloaded - see AGENTS.md), so "running" it here means
replicating its logic directly against the same synthetic panel, fast
and without another paid agent call. last_visit_date/last_a1c_date are
not in the panel CSV, so they're generated deterministically (seeded by
patient id) rather than randomly, so repeated runs are stable.
"""

import csv
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

from app.storage import create_visit, log_activity, save_visit

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


def run_diabetes_tracker() -> dict:
    now = datetime.now()
    patients = []
    with PANEL_CSV.open() as f:
        for row in csv.DictReader(f):
            if "diabetes" not in row.get("conditions", "").lower():
                continue
            visit_days_ago = _deterministic_days_ago(row["id"] + "visit", 365)
            a1c_days_ago = _deterministic_days_ago(row["id"] + "a1c", 420)
            overdue = a1c_days_ago > OVERDUE_DAYS
            patients.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "age": int(row["age"]),
                    "last_visit_date": (now - timedelta(days=visit_days_ago)).strftime("%Y-%m-%d"),
                    "last_a1c": row.get("last_a1c") or None,
                    "last_a1c_date": (now - timedelta(days=a1c_days_ago)).strftime("%Y-%m-%d"),
                    "overdue": overdue,
                }
            )
    patients.sort(key=lambda p: p["name"])
    return {
        "total": len(patients),
        "overdue_count": sum(1 for p in patients if p["overdue"]),
        "patients": patients,
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
