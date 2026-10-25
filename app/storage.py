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

VISITS_DIR = ROOT / "data" / "visits"
RUNS_DIR = ROOT / "runs"

TOOLS_DIR = ROOT / "data" / "tools"
TOOLS_REGISTRY_FILE = TOOLS_DIR / "registry.json"

ACTIVITY_FILE = ROOT / "data" / "activity.jsonl"


def _new_id(prefix: str = "") -> str:
    return (prefix + "_" if prefix else "") + uuid.uuid4().hex[:10]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------- Practice ----------

DEFAULT_PRACTICE = {
    "name": "Solo",
    "tagline": "Practice solo. Never alone.",
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
    }
    save_visit(visit)
    return visit


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
    visits.sort(key=lambda v: v.get("created_at", ""), reverse=True)
    return visits


def save_run_log(visit_id: str, run: dict) -> str:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = _new_id()
    path = RUNS_DIR / f"{visit_id}_{run_id}.json"
    path.write_text(json.dumps(run, indent=2))
    return run_id


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


def add_tool(tool: dict) -> dict:
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    tools = list_tools()
    tool = {"id": _new_id("tool"), "created_at": now_iso(), **tool}
    tools.insert(0, tool)
    TOOLS_REGISTRY_FILE.write_text(json.dumps(tools, indent=2))
    return tool


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
