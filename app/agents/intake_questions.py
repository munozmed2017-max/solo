"""Adaptive intake questions for the booking page.

After the patient types a reason for visit, the intake agent (FAST model,
thinking_level=low) generates 1-3 targeted follow-up questions - duration
and current medications are always included, added in code rather than
left to the model, so they're guaranteed present even if the model
forgets. If generation takes longer than TIMEOUT_SECONDS or fails for any
reason, callers get the fixed FALLBACK_QUESTIONS instead.
"""

import concurrent.futures
import json

from app.agents.base import load_prompt
from app.models import call_model

ROLE = "intake"
THINKING_LEVEL = "low"
TIMEOUT_SECONDS = 8

DURATION_Q = {"id": "duration", "text": "How long have you had this?", "type": "text"}
MEDS_Q = {"id": "current_medications", "text": "What medications are you currently taking?", "type": "text"}

FALLBACK_QUESTIONS = [
    DURATION_Q,
    {"id": "severity", "text": "On a scale of 0 to 10, how severe is it?", "type": "scale_0_10"},
    {"id": "fever", "text": "Do you have a fever?", "type": "yes_no"},
    MEDS_Q,
    {"id": "allergies", "text": "Do you have any allergies?", "type": "yes_no"},
]

QUESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "text": {"type": "string"},
                    "type": {"type": "string", "enum": ["yes_no", "scale_0_10", "text"]},
                },
                "required": ["id", "text", "type"],
            },
        }
    },
    "required": ["questions"],
}


def _generate(reason: str) -> dict:
    interaction = call_model(
        ROLE,
        f"Reason for visit: {reason}",
        thinking_level=THINKING_LEVEL,
        system_instruction=load_prompt("intake_questions"),
        response_format={"type": "text", "mime_type": "application/json", "schema": QUESTIONS_SCHEMA},
    )
    data = json.loads(interaction.output_text)
    extra = [
        q
        for q in data.get("questions", [])[:3]
        if q.get("id") not in ("duration", "current_medications") and q.get("text")
    ]
    return {"questions": [DURATION_Q, MEDS_Q] + extra, "source": "generated"}


def get_questions(reason: str) -> dict:
    """Always returns within ~TIMEOUT_SECONDS: either a generated set or
    FALLBACK_QUESTIONS. The orphaned generation thread (if it timed out)
    is left to finish on its own - it's a pure function, nothing to clean
    up, and its result is simply discarded."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(_generate, reason)
        try:
            return future.result(timeout=TIMEOUT_SECONDS)
        except Exception:
            return {"questions": FALLBACK_QUESTIONS, "source": "fallback"}
