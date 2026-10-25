"""Fixed sequential pipeline per case.

Order matters clinically: prescription must exist before prior-auth can
reference a specific medication, and the verifier runs last so it can
review everything, including the prior-auth draft, before the patient
email goes out.
"""

from app.agents import emails, intake, prescription, prior_auth, scribe, verifier
from app.models import model_for_role
from app.storage import save_case, save_run_log

PIPELINE = [
    ("intake", intake),
    ("scribe", scribe),
    ("prescription", prescription),
    ("prior_auth", prior_auth),
    ("verifier", verifier),
    ("emails", emails),
]


def run_pipeline(case: dict) -> dict:
    run_log = {"case_id": case["id"], "steps": []}
    done = {s["agent"] for s in case["steps"]}
    for agent_name, module in PIPELINE:
        if agent_name in done:
            continue
        output = module.run(case)
        step = {
            "agent": agent_name,
            "model": model_for_role(agent_name),
            "thinking_level": module.THINKING_LEVEL,
            "output": output,
            "approved": None,
        }
        case["steps"].append(step)
        run_log["steps"].append(step)
        save_case(case)
    case["status"] = "reviewed" if len(case["steps"]) == len(PIPELINE) else "in_progress"
    save_case(case)
    save_run_log(case["id"], run_log)
    return case
