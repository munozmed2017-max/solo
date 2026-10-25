from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text()


def step_output(case: dict, agent: str) -> str:
    for step in case["steps"]:
        if step["agent"] == agent:
            return step["output"]
    return ""
