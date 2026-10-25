import json
import re
from pathlib import Path

from app.agents.base import load_prompt
from app.models import LEAD, call_antigravity
from app.storage import add_tool

ROLE = "agent_builder"

DEMO_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "demo"
PANEL_CSV_PATH = DEMO_DIR / "synthetic_panel_2500.csv"
PANEL_META_PATH = DEMO_DIR / "synthetic_panel_meta.json"


def _true_diabetic_count() -> int:
    return json.loads(PANEL_META_PATH.read_text())["true_diabetic_count"]


def _extract(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(1).strip() if m else None


MAX_FOLLOWUPS = 3

FOLLOWUP_PROMPT = (
    "Wrap up now: you already wrote and ran the tool and its test. Do not "
    "write or run any more code. In your next reply, just summarize what "
    "you found and the test result, then output the required final two "
    "lines:\nFINAL_COUNT: <integer>\nTESTS_PASSED: <true or false>"
)


def run(description: str) -> dict:
    """Actually build and test a new back-office tool via a real Antigravity
    managed agent run (gemini-4-argon underneath), tested against a real
    synthetic 2,500-patient panel - not mocked. See AGENTS.md.

    A single call often comes back `status: "incomplete"` with empty
    output_text even after the real work (writing the tool, testing it,
    running it against the panel) already succeeded - Antigravity's
    per-turn step budget runs out before it writes the wrap-up summary.
    When that happens we send a short follow-up in the same sandbox
    asking it to just report what it already found, rather than treating
    the run as failed.
    """
    instruction = (
        f"{load_prompt(ROLE)}\n\n"
        f"New back-office tool to build and test:\n{description}\n\n"
        "--- panel.csv (write this exact content to a file named panel.csv, "
        "then test your tool against it) ---\n"
        f"{PANEL_CSV_PATH.read_text()}\n"
        "--- end panel.csv ---\n"
    )
    interaction = call_antigravity(instruction, model=LEAD, max_total_tokens=500_000)

    followups = 0
    while not (interaction.output_text or "").strip() and followups < MAX_FOLLOWUPS:
        followups += 1
        interaction = call_antigravity(
            FOLLOWUP_PROMPT,
            model=LEAD,
            max_total_tokens=100_000,
            previous_interaction_id=interaction.id,
            environment_id=interaction.environment_id,
        )

    output = interaction.output_text or ""

    final_count_str = _extract(r"FINAL_COUNT:\s*(\d+)", output)
    tests_passed_str = _extract(r"TESTS_PASSED:\s*(true|false)", output)
    final_count = int(final_count_str) if final_count_str is not None else None
    tests_passed = (tests_passed_str == "true") if tests_passed_str else None

    true_count = _true_diabetic_count() if "diabet" in description.lower() else None
    count_matches = (
        (final_count == true_count) if (final_count is not None and true_count is not None) else None
    )

    return add_tool(
        {
            "description": description,
            "status": interaction.status,
            "tests_passed": tests_passed,
            "final_count": final_count,
            "true_count": true_count,
            "count_matches": count_matches,
            "output": output,
            "environment_id": interaction.environment_id,
            "interaction_id": interaction.id,
        }
    )
