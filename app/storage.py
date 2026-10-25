"""Flat-file JSON storage for cases, patient panel, and run logs.

No database for v1 - single physician, low volume. Cases live one-file-
per-case under data/cases/ so they're easy to inspect/gitignore. The panel
is a single JSON list under data/panel/panel.json, seeded from
data/demo/panel_seed.json on first run.
"""

import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES_DIR = ROOT / "data" / "cases"
PANEL_DIR = ROOT / "data" / "panel"
DEMO_DIR = ROOT / "data" / "demo"
RUNS_DIR = ROOT / "runs"

PANEL_FILE = PANEL_DIR / "panel.json"
PANEL_SEED_FILE = DEMO_DIR / "panel_seed.json"


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def ensure_panel_seeded() -> None:
    if PANEL_FILE.exists():
        return
    PANEL_DIR.mkdir(parents=True, exist_ok=True)
    if PANEL_SEED_FILE.exists():
        seed = json.loads(PANEL_SEED_FILE.read_text())
    else:
        seed = []
    PANEL_FILE.write_text(json.dumps(seed, indent=2))


def list_panel() -> list[dict]:
    ensure_panel_seeded()
    return json.loads(PANEL_FILE.read_text())


def add_patient(patient: dict) -> dict:
    panel = list_panel()
    patient = {"id": _new_id(), **patient}
    panel.append(patient)
    PANEL_FILE.write_text(json.dumps(panel, indent=2))
    return patient


def get_patient(patient_id: str) -> dict | None:
    for p in list_panel():
        if p["id"] == patient_id:
            return p
    return None


def _case_path(case_id: str) -> Path:
    return CASES_DIR / f"{case_id}.json"


def create_case(patient: dict, reason: str, notes: str) -> dict:
    CASES_DIR.mkdir(parents=True, exist_ok=True)
    case = {
        "id": _new_id(),
        "patient": patient,
        "reason": reason,
        "notes": notes,
        "status": "new",
        "steps": [],
    }
    save_case(case)
    return case


def save_case(case: dict) -> None:
    CASES_DIR.mkdir(parents=True, exist_ok=True)
    _case_path(case["id"]).write_text(json.dumps(case, indent=2))


def get_case(case_id: str) -> dict | None:
    path = _case_path(case_id)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def list_cases() -> list[dict]:
    if not CASES_DIR.exists():
        return []
    cases = [json.loads(p.read_text()) for p in CASES_DIR.glob("*.json")]
    cases.sort(key=lambda c: c.get("id", ""), reverse=True)
    return cases


def save_run_log(case_id: str, run: dict) -> str:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = _new_id()
    path = RUNS_DIR / f"{case_id}_{run_id}.json"
    path.write_text(json.dumps(run, indent=2))
    return run_id
