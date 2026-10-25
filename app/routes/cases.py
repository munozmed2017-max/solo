from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agents.agent_builder import run as agent_builder_run
from app.orchestrator import run_pipeline
from app.storage import (
    add_patient,
    create_case,
    get_case,
    get_patient,
    list_cases,
    list_panel,
    save_case,
)

router = APIRouter(prefix="/api")


class NewPatient(BaseModel):
    name: str
    dob: str
    insurer: str = ""
    conditions: list[str] = []
    meds: list[str] = []


class NewCase(BaseModel):
    patient_id: str
    reason: str
    notes: str


class StepReview(BaseModel):
    approved: bool
    comment: str = ""


class AgentBuilderRequest(BaseModel):
    description: str


@router.get("/panel")
def api_list_panel():
    return list_panel()


@router.post("/panel")
def api_add_patient(patient: NewPatient):
    return add_patient(patient.model_dump())


@router.get("/cases")
def api_list_cases():
    cases = list_cases()
    return [
        {
            "id": c["id"],
            "patient_name": c["patient"].get("name"),
            "reason": c["reason"],
            "status": c["status"],
            "step_count": len(c["steps"]),
        }
        for c in cases
    ]


@router.post("/cases")
def api_create_case(new_case: NewCase):
    patient = get_patient(new_case.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Unknown patient")
    return create_case(patient, new_case.reason, new_case.notes)


@router.get("/cases/{case_id}")
def api_get_case(case_id: str):
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@router.post("/cases/{case_id}/run")
def api_run_case(case_id: str):
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return run_pipeline(case)


@router.post("/cases/{case_id}/steps/{step_index}/review")
def api_review_step(case_id: str, step_index: int, review: StepReview):
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if step_index < 0 or step_index >= len(case["steps"]):
        raise HTTPException(status_code=404, detail="Step not found")
    case["steps"][step_index]["approved"] = review.approved
    case["steps"][step_index]["comment"] = review.comment
    save_case(case)
    return case


@router.post("/agent-builder")
def api_agent_builder(req: AgentBuilderRequest):
    return {"draft": agent_builder_run(req.description)}
