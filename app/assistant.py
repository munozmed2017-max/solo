"""Ask Solo: a fast function-calling assistant over the physician dashboard.

gemini-3.8-flash picks one of a small, fixed set of real tools; we execute
it in plain Python (no extra model round-trip for a "final summary" - this
is explicitly the fast path) and return a structured result plus a
human-readable message. It never gives medical advice, and the only tool
that creates patient-facing content (draft_patient_email) only ever
produces a pending Approval-queue item - nothing is ever sent from here.
"""

import csv
from datetime import datetime, timedelta
from pathlib import Path

from app.models import FAST, call_model, get_client
from app.storage import get_visit, list_panel, list_tools, list_visits, log_activity, save_visit

SYNTHETIC_PANEL_CSV = Path(__file__).resolve().parent.parent / "data" / "demo" / "synthetic_panel_2500.csv"

SYSTEM_INSTRUCTION = (
    "You are Ask Solo, a command assistant for a solo physician's telemedicine "
    "dashboard. You ONLY act by calling exactly one of the provided tools based "
    "on the physician's request - you never answer from your own knowledge, you "
    "never give medical advice or clinical opinions, and you never claim to send "
    "anything (nothing is ever sent without separate physician approval). If the "
    "request doesn't clearly match a tool, call find_patients with the most "
    "relevant search text so the physician gets something useful back."
)

TOOLS = [
    {
        "type": "function",
        "name": "show_schedule",
        "description": "List appointments for a given day with time, patient, reason, and paid status.",
        "parameters": {
            "type": "object",
            "properties": {"day": {"type": "string", "description": "'today', 'tomorrow', or a date like 2026-10-26"}},
            "required": ["day"],
        },
    },
    {
        "type": "function",
        "name": "open_visit",
        "description": "Open a patient's visit screen.",
        "parameters": {"type": "object", "properties": {"patient": {"type": "string"}}, "required": ["patient"]},
    },
    {
        "type": "function",
        "name": "draft_patient_email",
        "description": (
            "Draft a follow-up email to a patient about a topic, grounded in their visit's "
            "approved plan and clinical summary. The draft goes to the Approval queue - it is "
            "never sent directly."
        ),
        "parameters": {
            "type": "object",
            "properties": {"patient": {"type": "string"}, "topic": {"type": "string"}},
            "required": ["patient", "topic"],
        },
    },
    {
        "type": "function",
        "name": "print_visit_summary",
        "description": "Open a clean printable page of a patient's visit summary.",
        "parameters": {"type": "object", "properties": {"patient": {"type": "string"}}, "required": ["patient"]},
    },
    {
        "type": "function",
        "name": "run_tool",
        "description": "Show the results of a previously built back-office tool (e.g. the diabetes tracker) by name.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    },
    {
        "type": "function",
        "name": "find_patients",
        "description": "Search visits and the patient panel for matching patients.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    },
]


def _find_visit_by_patient(patient: str) -> dict | None:
    needle = patient.strip().lower()
    matches = [v for v in list_visits() if needle in v["patient"].get("name", "").lower()]
    return matches[0] if matches else None


def _tool_show_schedule(args: dict) -> dict:
    day = (args.get("day") or "today").strip().lower()
    now = datetime.now()
    if day == "today":
        target = now.date()
    elif day == "tomorrow":
        target = (now + timedelta(days=1)).date()
    else:
        try:
            target = datetime.fromisoformat(day).date()
        except ValueError:
            target = now.date()
    rows = []
    for v in list_visits():
        at = v.get("appointment_time")
        if at and datetime.fromisoformat(at).date() == target:
            rows.append(
                {
                    "time": datetime.fromisoformat(at).strftime("%-I:%M %p"),
                    "patient": v["patient"].get("name"),
                    "reason": v["booking"].get("reason"),
                    "paid": v.get("payment_status") == "paid (simulated)",
                }
            )
    rows.sort(key=lambda r: r["time"])
    return {"day": str(target), "appointments": rows}


def _tool_open_visit(args: dict) -> dict:
    visit = _find_visit_by_patient(args.get("patient", ""))
    if not visit:
        return {"found": False}
    return {"found": True, "visit_id": visit["id"], "patient": visit["patient"].get("name")}


def _tool_draft_patient_email(args: dict) -> dict:
    patient = args.get("patient", "")
    topic = args.get("topic", "")
    visit_summary = _find_visit_by_patient(patient)
    if not visit_summary:
        return {"found": False}
    visit = get_visit(visit_summary["id"])
    scribe_note = visit["documents"].get("scribe", {}).get("output", "")
    plan = visit.get("physician_plan", "")
    prompt = (
        f"Patient: {visit['patient'].get('name')}\n"
        f"Clinical note:\n{scribe_note}\n\n"
        f"Physician's plan:\n{plan}\n\n"
        f"Topic the physician wants to follow up about: {topic}\n\n"
        "Write a short, warm, plain-language follow-up email to the patient about this "
        "topic. Only include instructions/information grounded in the clinical note or the "
        "physician's plan above - do not invent new advice."
    )
    interaction = call_model(
        "emails",
        prompt,
        thinking_level="low",
        system_instruction=(
            "You draft patient follow-up emails. Ground everything in the clinical note and "
            "physician's plan given to you. Never invent advice. Sign with the physician's name "
            "if given context allows it; otherwise sign 'Your care team'."
        ),
    )
    doc_key = "assistant_email"
    visit["documents"][doc_key] = {
        "output": interaction.output_text,
        "model": FAST,
        "thinking_level": "low",
        "resolved": True,
        "verification_rounds": [],
        "approval": {"status": "pending"},
        "sent": False,
    }
    save_visit(visit)
    return {"found": True, "visit_id": visit["id"], "patient": visit["patient"].get("name"), "doc_type": doc_key}


def _tool_print_visit_summary(args: dict) -> dict:
    visit = _find_visit_by_patient(args.get("patient", ""))
    if not visit:
        return {"found": False}
    return {"found": True, "visit_id": visit["id"], "patient": visit["patient"].get("name")}


def _tool_run_tool(args: dict) -> dict:
    name = (args.get("name") or "").strip().lower()
    for t in list_tools():
        if name in t["description"].lower():
            return {
                "found": True,
                "description": t["description"],
                "status": t["status"],
                "tests_passed": t["tests_passed"],
                "final_count": t["final_count"],
                "true_count": t["true_count"],
                "count_matches": t["count_matches"],
            }
    return {"found": False}


def _synthetic_panel_count(query: str) -> int | None:
    """The physician's actual two-person demo panel rarely has a condition
    match for a broad query like "diabetes" - also check the larger
    synthetic panel used by the agent builder so the answer is meaningful,
    not just technically-correct-but-empty."""
    if not SYNTHETIC_PANEL_CSV.exists():
        return None
    count = 0
    with SYNTHETIC_PANEL_CSV.open() as f:
        for row in csv.DictReader(f):
            if query in row.get("conditions", "").lower():
                count += 1
    return count


def _tool_find_patients(args: dict) -> dict:
    query = (args.get("query") or "").strip().lower()
    panel_matches = [
        p["name"]
        for p in list_panel()
        if query in p.get("name", "").lower() or any(query in c.lower() for c in p.get("conditions", []))
    ]
    visit_matches = [
        {"patient": v["patient"].get("name"), "reason": v["booking"].get("reason"), "visit_id": v["id"]}
        for v in list_visits()
        if query in v["patient"].get("name", "").lower() or query in v["booking"].get("reason", "").lower()
    ]
    result = {"panel_matches": panel_matches, "visit_matches": visit_matches}
    if not panel_matches and not visit_matches:
        synthetic_count = _synthetic_panel_count(query)
        if synthetic_count:
            result["synthetic_panel_count"] = synthetic_count
    return result


TOOL_EXECUTORS = {
    "show_schedule": _tool_show_schedule,
    "open_visit": _tool_open_visit,
    "draft_patient_email": _tool_draft_patient_email,
    "print_visit_summary": _tool_print_visit_summary,
    "run_tool": _tool_run_tool,
    "find_patients": _tool_find_patients,
}


def _message_for(tool_name: str, args: dict, result: dict) -> str:
    if tool_name == "show_schedule":
        n = len(result.get("appointments", []))
        return f"{n} appointment{'s' if n != 1 else ''} on {result.get('day')}."
    if tool_name == "open_visit":
        return f"Opening {result['patient']}'s visit." if result.get("found") else "Couldn't find that patient."
    if tool_name == "draft_patient_email":
        return f"Draft ready for {result['patient']}: Approve in queue." if result.get("found") else "Couldn't find that patient's visit."
    if tool_name == "print_visit_summary":
        return f"Opening a printable summary for {result['patient']}." if result.get("found") else "Couldn't find that patient."
    if tool_name == "run_tool":
        if not result.get("found"):
            return "No built tool matched that name."
        return f"{result['description']} - status: {result['status']}, tests_passed: {result['tests_passed']}."
    if tool_name == "find_patients":
        n = len(result.get("panel_matches", [])) + len(result.get("visit_matches", []))
        if n == 0 and result.get("synthetic_panel_count"):
            return f"None in your active panel/visits, but {result['synthetic_panel_count']} in the synthetic 2,500-patient panel match."
        return f"Found {n} match{'es' if n != 1 else ''}."
    return "Done."


def ask(query: str) -> dict:
    client = get_client()
    interaction = client.interactions.create(
        model=FAST,
        input=query,
        system_instruction=SYSTEM_INSTRUCTION,
        generation_config={"thinking_level": "low"},
        tools=TOOLS,
    )
    fc_step = next((s for s in interaction.steps if getattr(s, "type", None) == "function_call"), None)
    if not fc_step:
        log_activity("Assistant (gemini-3.8-flash)", "no tool matched", detail=query)
        return {"tool": None, "message": interaction.output_text or "I didn't understand that.", "data": {}}

    executor = TOOL_EXECUTORS.get(fc_step.name)
    result = executor(fc_step.arguments or {}) if executor else {}
    message = _message_for(fc_step.name, fc_step.arguments or {}, result)
    log_activity("Assistant (gemini-3.8-flash)", f"{fc_step.name}({fc_step.arguments})", detail=message)
    return {"tool": fc_step.name, "args": fc_step.arguments, "message": message, "data": result}
