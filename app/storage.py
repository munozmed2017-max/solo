"""Flat-file JSON storage for Solo.

Practice config, patient panel, visits (with their documents/approvals),
demo flags, the agent-builder tool registry, and an append-only activity
log. No database - single physician, low volume.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PRACTICE_DIR = ROOT / "data" / "practice"
PRACTICE_FILE = PRACTICE_DIR / "practice.json"

PANEL_DIR = ROOT / "data" / "panel"
PANEL_FILE = PANEL_DIR / "panel.json"

DEMO_DIR = ROOT / "data" / "demo"
PANEL_SEED_FILE = DEMO_DIR / "panel_seed.json"
FLAGS_FILE = DEMO_DIR / "flags.json"
MARGARET_SEED_FILE = DEMO_DIR / "margaret_visit_seed.json"

VISITS_DIR = ROOT / "data" / "visits"
RUNS_DIR = ROOT / "runs"

TOOLS_DIR = ROOT / "data" / "tools"
TOOLS_REGISTRY_FILE = TOOLS_DIR / "registry.json"

RESULTS_DIR = ROOT / "data" / "results"
RESULTS_FILE = RESULTS_DIR / "latest.json"

ACTIVITY_FILE = ROOT / "data" / "activity.jsonl"


def _new_id(prefix: str = "") -> str:
    return (prefix + "_" if prefix else "") + uuid.uuid4().hex[:10]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------- Practice ----------

DEFAULT_PRACTICE = {
    "name": "Dr. Munoz Clinic",
    "physician_name": "Dr. Jhonatan Munoz",
    "hours": "Mon-Fri 9am-5pm",
    "visit_fee": "$75",
    "booking_path": "/book",
}


def get_practice() -> dict:
    PRACTICE_DIR.mkdir(parents=True, exist_ok=True)
    if not PRACTICE_FILE.exists():
        PRACTICE_FILE.write_text(json.dumps(DEFAULT_PRACTICE, indent=2))
    return json.loads(PRACTICE_FILE.read_text())


def save_practice(practice: dict) -> dict:
    PRACTICE_DIR.mkdir(parents=True, exist_ok=True)
    PRACTICE_FILE.write_text(json.dumps(practice, indent=2))
    return practice


# ---------- Patient panel ----------

def ensure_panel_seeded() -> None:
    PANEL_DIR.mkdir(parents=True, exist_ok=True)
    if PANEL_FILE.exists():
        return
    seed = json.loads(PANEL_SEED_FILE.read_text()) if PANEL_SEED_FILE.exists() else []
    PANEL_FILE.write_text(json.dumps(seed, indent=2))


def list_panel() -> list[dict]:
    ensure_panel_seeded()
    return json.loads(PANEL_FILE.read_text())


def find_patient(name: str, dob: str | None = None) -> dict | None:
    name_norm = (name or "").strip().lower()
    for p in list_panel():
        if p.get("name", "").strip().lower() == name_norm:
            if dob and p.get("dob") and p["dob"] != dob:
                continue
            return p
    return None


# ---------- Visits ----------

def _visit_path(visit_id: str) -> Path:
    return VISITS_DIR / f"{visit_id}.json"


def create_visit(booking: dict) -> dict:
    VISITS_DIR.mkdir(parents=True, exist_ok=True)
    patient_record = find_patient(booking["name"], booking.get("dob")) or {
        "name": booking["name"],
        "dob": booking.get("dob"),
        "conditions": [],
        "meds": [],
        "labs": [],
        "vitals": {},
    }
    visit = {
        "id": _new_id("visit"),
        "created_at": now_iso(),
        "patient": patient_record,
        "booking": {
            "name": booking["name"],
            "dob": booking.get("dob"),
            "reason": booking.get("reason", ""),
            "symptoms": booking.get("symptoms", {}),
            "uploaded_files": booking.get("uploaded_files", []),
        },
        "status": "booked",
        "intake_summary": None,
        "transcript": booking.get("transcript_prefill", ""),
        "physician_plan": booking.get("plan_prefill", ""),
        "documents": {},
        "needs_manual_review": False,
        "appointment_time": booking.get("appointment_time") or None,
        "payment_status": "unpaid",
        "paid_amount": None,
    }
    save_visit(visit)
    return visit


def mark_visit_paid(visit_id: str, amount: str) -> dict:
    visit = get_visit(visit_id)
    if not visit:
        raise ValueError("visit not found")
    visit["payment_status"] = "paid (simulated)"
    visit["paid_amount"] = amount
    visit["paid_at"] = now_iso()
    save_visit(visit)
    return visit


def get_earnings() -> dict:
    paid = [v for v in list_visits() if v.get("payment_status") == "paid (simulated)"]
    total = 0.0
    for v in paid:
        try:
            total += float(str(v.get("paid_amount", "0")).replace("$", "").strip())
        except ValueError:
            pass
    return {"paid_visit_count": len(paid), "total_amount": round(total, 2)}


def save_visit(visit: dict) -> None:
    VISITS_DIR.mkdir(parents=True, exist_ok=True)
    _visit_path(visit["id"]).write_text(json.dumps(visit, indent=2))


def get_visit(visit_id: str) -> dict | None:
    path = _visit_path(visit_id)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def list_visits() -> list[dict]:
    if not VISITS_DIR.exists():
        return []
    visits = [json.loads(p.read_text()) for p in VISITS_DIR.glob("*.json")]
    # Scheduled visits sort by appointment time (soonest first); visits with
    # no appointment_time (e.g. Margaret's demo case) sort after, newest first.
    scheduled = sorted((v for v in visits if v.get("appointment_time")), key=lambda v: v["appointment_time"])
    unscheduled = sorted(
        (v for v in visits if not v.get("appointment_time")), key=lambda v: v.get("created_at", ""), reverse=True
    )
    return scheduled + unscheduled


def save_run_log(visit_id: str, run: dict) -> str:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = _new_id()
    path = RUNS_DIR / f"{visit_id}_{run_id}.json"
    path.write_text(json.dumps(run, indent=2))
    return run_id


def reset_demo() -> dict:
    """Clears all visits (and with them, their approvals) except Margaret's
    demo case, restored from the fixed seed captured earlier. Deliberately
    does NOT touch the tools registry, results run, or practice settings -
    those are expensive/slow to regenerate and aren't part of what "reset"
    means here."""
    if VISITS_DIR.exists():
        for f in VISITS_DIR.glob("*.json"):
            f.unlink()
    VISITS_DIR.mkdir(parents=True, exist_ok=True)
    (VISITS_DIR / ".gitkeep").write_text("")
    restored = False
    if MARGARET_SEED_FILE.exists():
        seed = json.loads(MARGARET_SEED_FILE.read_text())
        _visit_path(seed["id"]).write_text(json.dumps(seed, indent=2))
        restored = True
    log_activity("physician", "reset demo data (visits/approvals cleared, Margaret's case restored)")
    return {"margaret_restored": restored}


# ---------- Approval queue (derived from visits' documents) ----------

def list_approval_items() -> list[dict]:
    items = []
    for visit in list_visits():
        for doc_type, doc in visit.get("documents", {}).items():
            items.append(
                {
                    "visit_id": visit["id"],
                    "patient_name": visit["patient"].get("name"),
                    "doc_type": doc_type,
                    "status": doc.get("approval", {}).get("status", "pending"),
                    "resolved": doc.get("resolved"),
                    "output": doc.get("output"),
                    "sent": doc.get("sent", False),
                }
            )
    return items


def set_document_approval(
    visit_id: str, doc_type: str, status: str, edited_text: str | None, comment: str
) -> dict:
    visit = get_visit(visit_id)
    if not visit or doc_type not in visit.get("documents", {}):
        raise ValueError("document not found")
    doc = visit["documents"][doc_type]
    if edited_text:
        doc["output"] = edited_text
    doc["approval"] = {
        "status": status,
        "comment": comment,
        "decided_at": now_iso(),
    }
    save_visit(visit)
    return visit


def mark_document_sent(visit_id: str, doc_type: str) -> dict:
    """Enforced in code: raises unless the document carries an approval record."""
    visit = get_visit(visit_id)
    if not visit or doc_type not in visit.get("documents", {}):
        raise ValueError("document not found")
    doc = visit["documents"][doc_type]
    approval = doc.get("approval")
    if not approval or approval.get("status") != "approved":
        raise PermissionError("cannot send a document without an approval record")
    doc["sent"] = True
    doc["sent_at"] = now_iso()
    save_visit(visit)
    return visit


# ---------- Demo flags ----------

DEFAULT_FLAGS = {"DEMO_PLANTED_ERROR": False}


def get_flags() -> dict:
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    if not FLAGS_FILE.exists():
        FLAGS_FILE.write_text(json.dumps(DEFAULT_FLAGS, indent=2))
    return json.loads(FLAGS_FILE.read_text())


def set_flag(key: str, value) -> dict:
    flags = get_flags()
    flags[key] = value
    FLAGS_FILE.write_text(json.dumps(flags, indent=2))
    return flags


# ---------- Tools registry (agent builder) ----------

def list_tools() -> list[dict]:
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    if not TOOLS_REGISTRY_FILE.exists():
        return []
    return json.loads(TOOLS_REGISTRY_FILE.read_text())


def start_tool_build(description: str) -> dict:
    """Create a tool record immediately, before the (possibly minutes-long)
    build finishes, so the UI can poll it for live progress and it's
    already on disk if the server restarts mid-build."""
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    tools = list_tools()
    tool = {
        "id": _new_id("tool"),
        "created_at": now_iso(),
        "description": description,
        "status": "in_progress",
        "progress_label": "Starting sandbox...",
        "tests_passed": None,
        "final_count": None,
        "true_count": None,
        "count_matches": None,
        "output": None,
        "environment_id": None,
        "interaction_id": None,
    }
    tools.insert(0, tool)
    TOOLS_REGISTRY_FILE.write_text(json.dumps(tools, indent=2))
    return tool


def get_tool(tool_id: str) -> dict | None:
    for t in list_tools():
        if t["id"] == tool_id:
            return t
    return None


def update_tool(tool_id: str, patch: dict) -> dict:
    tools = list_tools()
    for t in tools:
        if t["id"] == tool_id:
            t.update(patch)
            TOOLS_REGISTRY_FILE.write_text(json.dumps(tools, indent=2))
            return t
    raise ValueError("tool not found")


# ---------- Results batch run ----------

def start_results_run(total_units: int) -> dict:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "status": "in_progress",
        "completed": 0,
        "total": total_units,
        "started_at": now_iso(),
        "table": None,
    }
    RESULTS_FILE.write_text(json.dumps(record, indent=2))
    return record


def get_results_run() -> dict | None:
    if not RESULTS_FILE.exists():
        return None
    return json.loads(RESULTS_FILE.read_text())


def bump_results_progress() -> dict:
    record = get_results_run() or {}
    record["completed"] = record.get("completed", 0) + 1
    RESULTS_FILE.write_text(json.dumps(record, indent=2))
    return record


def finish_results_run(table: list, elapsed_seconds: float) -> dict:
    record = get_results_run() or {}
    record["status"] = "completed"
    record["table"] = table
    record["elapsed_seconds"] = elapsed_seconds
    record["finished_at"] = now_iso()
    RESULTS_FILE.write_text(json.dumps(record, indent=2))
    return record


def fail_results_run(error: str) -> dict:
    record = get_results_run() or {}
    record["status"] = "failed"
    record["error"] = error
    RESULTS_FILE.write_text(json.dumps(record, indent=2))
    return record


# ---------- Activity log ----------

def log_activity(actor: str, action: str, detail: str = "", visit_id: str | None = None) -> dict:
    entry = {
        "time": now_iso(),
        "actor": actor,
        "action": action,
        "detail": detail,
        "visit_id": visit_id,
    }
    ACTIVITY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with ACTIVITY_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_activity(limit: int = 200) -> list[dict]:
    if not ACTIVITY_FILE.exists():
        return []
    lines = ACTIVITY_FILE.read_text().splitlines()
    entries = [json.loads(line) for line in lines if line.strip()]
    entries.reverse()
    return entries[:limit]
