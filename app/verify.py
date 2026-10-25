"""Shared verify-and-revise loop used by every drafting agent in the pipeline.

The verifier is blocking, not flag-only: it checks a document sentence by
sentence against ground-truth context. A failure goes back to the same
agent that wrote the document, with the specific failing sentences and
reasons, to rewrite. This repeats up to MAX_ROUNDS times; every round
(draft + verifier verdict) is logged on the case step so the physician can
see exactly what was wrong and how it was fixed - or that it was never
fully resolved.
"""

from app.agents import verifier
from app.agents.base import load_prompt
from app.models import call_model

MAX_ROUNDS = 3


def _draft(module, input_text: str) -> str:
    interaction = call_model(
        module.ROLE,
        input_text,
        thinking_level=module.THINKING_LEVEL,
        system_instruction=load_prompt(module.ROLE),
    )
    return interaction.output_text


def _revise(module, base_input: str, previous_draft: str, failures: list) -> str:
    failures_text = "\n".join(f'- "{f.sentence}": {f.reason}' for f in failures) or "(none)"
    revision_input = (
        f"{base_input}\n\n"
        f"--- Previous draft (sent back by the verifier) ---\n{previous_draft}\n\n"
        f"--- Sentences the verifier failed, and why ---\n{failures_text}\n\n"
        "Rewrite the full document, fixing every issue listed above. Keep "
        "everything the verifier did not flag as-is. Output only the "
        "corrected document, nothing else."
    )
    return _draft(module, revision_input)


def run_with_verification(module, case: dict, patient_chart: str) -> dict:
    """Draft `module`'s document for `case`, then verify/revise up to MAX_ROUNDS times.

    Returns {"output": final draft text, "resolved": bool, "rounds": [...]}.
    `resolved` is False if the verifier still failed the document after the
    last round - the physician must review it manually in that case.
    """
    base_input = module.build_input(case)
    draft_text = _draft(module, base_input)
    context = f"{patient_chart}\n\n{base_input}"

    rounds = []
    for round_num in range(1, MAX_ROUNDS + 1):
        result = verifier.check(module.ROLE, draft_text, context)
        rounds.append(
            {
                "round": round_num,
                "draft": draft_text,
                "passed": result.passed,
                "failures": [f.model_dump() for f in result.failures],
            }
        )
        if result.passed or round_num == MAX_ROUNDS:
            break
        draft_text = _revise(module, base_input, draft_text, result.failures)

    return {"output": draft_text, "resolved": rounds[-1]["passed"], "rounds": rounds}
