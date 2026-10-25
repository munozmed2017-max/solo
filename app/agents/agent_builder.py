import json
import re
import threading
from pathlib import Path

from app.agents.base import load_prompt
from app.models import LEAD, call_antigravity, call_antigravity_stream, get_interaction
from app.storage import get_tool, log_activity, start_tool_build, update_tool

ROLE = "agent_builder"

DEMO_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "demo"
PANEL_CSV_PATH = DEMO_DIR / "synthetic_panel_2500.csv"
PANEL_META_PATH = DEMO_DIR / "synthetic_panel_meta.json"

MAX_FOLLOWUPS = 3

FOLLOWUP_PROMPT = (
    "Wrap up now: you already wrote and ran the tool and its test. Do not "
    "write or run any more code. In your next reply, just summarize what "
    "you found and the test result, then output the required final two "
    "lines:\nFINAL_COUNT: <integer>\nTESTS_PASSED: <true or false>"
)


def _true_diabetic_count() -> int:
    return json.loads(PANEL_META_PATH.read_text())["true_diabetic_count"]


def _extract(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(1).strip() if m else None


def _label_for_step(step) -> str:
    """Human-readable progress from the real step Antigravity just started -
    not a simulated/fake progress bar."""
    step_type = getattr(step, "type", None)
    name = (getattr(step, "name", "") or "").lower()
    if step_type == "function_call":
        if "write" in name:
            return "Writing code..."
        if "run" in name or "execute" in name:
            return "Running code..."
        if "view" in name or "read" in name:
            return "Reading files..."
        return f"Calling {name or 'tool'}..."
    if step_type == "function_result":
        return "Step finished, continuing..."
    if step_type == "code_execution_call":
        return "Running tests..."
    if step_type == "code_execution_result":
        return "Reviewing test results..."
    if step_type == "model_output":
        return "Summarizing results..."
    if step_type == "thought":
        return "Thinking..."
    return f"Working ({step_type})..." if step_type else "Working..."


def _build_instruction(description: str) -> str:
    return (
        f"{load_prompt(ROLE)}\n\n"
        f"New back-office tool to build and test:\n{description}\n\n"
        "--- panel.csv (write this exact content to a file named panel.csv, "
        "then test your tool against it) ---\n"
        f"{PANEL_CSV_PATH.read_text()}\n"
        "--- end panel.csv ---\n"
    )


def start_build(description: str) -> dict:
    """Create the tool record and kick off the real build in a background
    thread, returning immediately so the caller can poll get_tool()
    (via GET /api/tools/{id}/status) for live progress."""
    tool = start_tool_build(description)
    threading.Thread(target=_run_build, args=(tool["id"], description), daemon=True).start()
    return tool


def poll_build(tool_id: str) -> dict:
    """The background thread already writes progress to storage as it
    happens, so polling is just a disk read - no extra API calls."""
    tool = get_tool(tool_id)
    if not tool:
        raise ValueError("tool not found")
    return tool


def _run_build(tool_id: str, description: str) -> None:
    try:
        stream = call_antigravity_stream(_build_instruction(description), model=LEAD, max_total_tokens=500_000)
        interaction_id = None
        environment_id = None
        for event in stream:
            event_type = getattr(event, "event_type", None)
            if event_type == "interaction.created":
                meta = getattr(event, "interaction", None)
                interaction_id = getattr(meta, "id", None)
                environment_id = getattr(meta, "environment_id", None)
                update_tool(
                    tool_id,
                    {
                        "interaction_id": interaction_id,
                        "environment_id": environment_id,
                        "progress_label": "Sandbox started...",
                    },
                )
            elif event_type == "step.start":
                step = getattr(event, "step", None)
                if step is not None:
                    update_tool(tool_id, {"progress_label": _label_for_step(step)})
            elif event_type == "interaction.completed":
                meta = getattr(event, "interaction", None)
                interaction_id = getattr(meta, "id", None) or interaction_id

        if not interaction_id:
            raise RuntimeError("stream ended without ever reporting an interaction id")
        # Re-fetch via the normal (non-streaming) SDK object for output_text
        # and other convenience properties _finalize() relies on.
        final_interaction = get_interaction(interaction_id)
        _finalize(tool_id, final_interaction)
    except Exception as e:  # background thread - must not raise silently into the void
        update_tool(tool_id, {"status": "failed", "progress_label": f"Error: {e}"})


def _finalize(tool_id: str, interaction, followups: int = 0) -> dict:
    """Interaction reached a terminal status. Antigravity often comes back
    with empty output_text here even though the real work already
    succeeded (confirmed by inspecting interaction.steps) - its per-turn
    step budget runs out before the wrap-up summary. Send a short
    same-sandbox follow-up asking it to just report what it found, rather
    than treating the run as failed. See AGENTS.md."""
    output = (interaction.output_text or "").strip()
    if not output and followups < MAX_FOLLOWUPS and interaction.status != "failed":
        update_tool(tool_id, {"progress_label": f"Summarizing results (attempt {followups + 1})..."})
        followup_interaction = call_antigravity(
            FOLLOWUP_PROMPT,
            model=LEAD,
            max_total_tokens=100_000,
            previous_interaction_id=interaction.id,
            environment_id=interaction.environment_id,
        )
        return _finalize(tool_id, followup_interaction, followups + 1)

    final_count_str = _extract(r"FINAL_COUNT:\s*(\d+)", output)
    tests_passed_str = _extract(r"TESTS_PASSED:\s*(true|false)", output)
    final_count = int(final_count_str) if final_count_str is not None else None
    tests_passed = (tests_passed_str == "true") if tests_passed_str else None

    tool = get_tool(tool_id)
    true_count = _true_diabetic_count() if "diabet" in tool["description"].lower() else None
    count_matches = (
        (final_count == true_count) if (final_count is not None and true_count is not None) else None
    )

    if final_count is not None and true_count is not None:
        progress_label = (
            f"Verified: {final_count} = {true_count}"
            if count_matches
            else f"Mismatch: {final_count} != {true_count}"
        )
    elif tests_passed is not None:
        progress_label = "Tests passed" if tests_passed else "Tests failed"
    else:
        progress_label = "Done"

    tool = update_tool(
        tool_id,
        {
            "status": interaction.status,
            "progress_label": progress_label,
            "tests_passed": tests_passed,
            "final_count": final_count,
            "true_count": true_count,
            "count_matches": count_matches,
            "output": output,
            "interaction_id": interaction.id,
            "environment_id": interaction.environment_id,
        },
    )
    log_activity(
        "agent builder",
        "tool build finished",
        detail=f"tests_passed={tests_passed} final_count={final_count}",
    )
    return tool
