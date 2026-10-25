"""Gemini model roster and the single call_model() helper every agent uses.

Model choice is role-based, not ad hoc: LEAD is used for roles that need
strong reasoning (orchestration, scribing, prior auth, verification, agent
building). FAST is used for high-volume/low-latency roles (intake,
prescriptions, emails) and as the baseline for anything unlisted.
"""

import os
from functools import lru_cache

from dotenv import load_dotenv
from google import genai

load_dotenv()

LEAD = "gemini-4-argon"
FAST = "gemini-3.8-flash"

# orchestrator/scribe/prior_auth/verifier/agent_builder -> LEAD
# intake/prescription/emails/baseline -> FAST
ROLE_MODELS = {
    "orchestrator": LEAD,
    "scribe": LEAD,
    "prior_auth": LEAD,
    "verifier": LEAD,
    "agent_builder": LEAD,
    "intake": FAST,
    "prescription": FAST,
    "emails": FAST,
    "baseline": FAST,
}

# 20 minutes, in milliseconds (google-genai HttpOptions.timeout is ms).
HTTP_TIMEOUT_MS = 20 * 60 * 1000

# Real managed agent used by agent_builder - not mocked. See AGENTS.md.
ANTIGRAVITY_AGENT = "antigravity-preview-09-2026"


@lru_cache(maxsize=1)
def get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Put it in .env at the project root."
        )
    return genai.Client(
        api_key=api_key,
        http_options={"timeout": HTTP_TIMEOUT_MS},
    )


def model_for_role(role: str) -> str:
    return ROLE_MODELS.get(role, FAST)


def call_model(
    role: str,
    input_text: str,
    thinking_level: str = "medium",
    system_instruction: str | None = None,
    previous_interaction_id: str | None = None,
    response_format: dict | None = None,
) -> genai.types.Interaction:
    """Run one Gemini interaction for the given back-office role.

    Never pass temperature/top_p/top_k/thinking_budget here - only
    thinking_level, per project convention.
    """
    client = get_client()
    model = model_for_role(role)
    kwargs = {
        "model": model,
        "input": input_text,
        "generation_config": {"thinking_level": thinking_level},
    }
    if system_instruction:
        kwargs["system_instruction"] = system_instruction
    if previous_interaction_id:
        kwargs["previous_interaction_id"] = previous_interaction_id
    if response_format:
        kwargs["response_format"] = response_format
    return client.interactions.create(**kwargs)


def call_antigravity(
    input_text: str,
    model: str = LEAD,
    max_total_tokens: int = 50_000,
    environment_id: str | None = None,
    previous_interaction_id: str | None = None,
) -> genai.types.Interaction:
    """Run a real Antigravity managed agent turn in a sandboxed Linux env.

    Used by agent_builder - it actually writes and executes code, it does
    not just draft text. `environment_id` reuses an existing sandbox
    (continuing a build); omit it to provision a fresh one.
    """
    client = get_client()
    kwargs = {
        "agent": ANTIGRAVITY_AGENT,
        "input": input_text,
        "environment": environment_id or "remote",
        "agent_config": {"type": "antigravity", "model": model, "max_total_tokens": max_total_tokens},
    }
    if previous_interaction_id:
        kwargs["previous_interaction_id"] = previous_interaction_id
    return client.interactions.create(**kwargs)


def call_antigravity_background(
    input_text: str,
    model: str = LEAD,
    max_total_tokens: int = 50_000,
    environment_id: str | None = None,
    previous_interaction_id: str | None = None,
) -> genai.types.Interaction:
    """Same as call_antigravity but returns immediately (background=True) so
    the caller can poll get_interaction() for live status/progress instead
    of blocking the request thread for minutes."""
    client = get_client()
    kwargs = {
        "agent": ANTIGRAVITY_AGENT,
        "input": input_text,
        "environment": environment_id or "remote",
        "agent_config": {"type": "antigravity", "model": model, "max_total_tokens": max_total_tokens},
        "background": True,
    }
    if previous_interaction_id:
        kwargs["previous_interaction_id"] = previous_interaction_id
    return client.interactions.create(**kwargs)


def get_interaction(interaction_id: str) -> genai.types.Interaction:
    return get_client().interactions.get(interaction_id)


def call_antigravity_stream(
    input_text: str,
    model: str = LEAD,
    max_total_tokens: int = 50_000,
    environment_id: str | None = None,
    previous_interaction_id: str | None = None,
):
    """Streaming variant - yields step.start/step.delta/... events in real
    time so a caller can report genuine progress instead of a fake
    spinner. See app.agents.agent_builder for the consumer."""
    client = get_client()
    kwargs = {
        "agent": ANTIGRAVITY_AGENT,
        "input": input_text,
        "environment": environment_id or "remote",
        "agent_config": {"type": "antigravity", "model": model, "max_total_tokens": max_total_tokens},
        "stream": True,
    }
    if previous_interaction_id:
        kwargs["previous_interaction_id"] = previous_interaction_id
    return client.interactions.create(**kwargs)
