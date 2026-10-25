from pydantic import BaseModel

from app.agents.base import load_prompt
from app.models import call_model

ROLE = "verifier"
THINKING_LEVEL = "high"

# Plain dict, not Failure.model_json_schema()/VerifierResult.model_json_schema():
# keeping this ref-free avoids relying on the API's $defs/$ref support for
# structured output.
RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "passed": {"type": "boolean"},
        "failures": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sentence": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["sentence", "reason"],
            },
        },
    },
    "required": ["passed", "failures"],
}


class Failure(BaseModel):
    sentence: str
    reason: str


class VerifierResult(BaseModel):
    passed: bool
    failures: list[Failure] = []


def check(document_label: str, document_text: str, context: str) -> VerifierResult:
    """Sentence-level pass/fail check of one document against ground truth.

    This blocks: a False `passed` is sent back to the drafting agent to
    rewrite (see app/verify.py), not just logged as a flag.
    """
    input_text = (
        f"Document under review ({document_label}):\n{document_text}\n\n"
        f"--- Ground-truth context ---\n{context}\n"
    )
    interaction = call_model(
        ROLE,
        input_text,
        thinking_level=THINKING_LEVEL,
        system_instruction=load_prompt(ROLE),
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": RESULT_SCHEMA,
        },
    )
    return VerifierResult.model_validate_json(interaction.output_text)
