from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.orchestrator import approve_visit, generate_intake
from app.storage import create_visit, get_visit, list_visits, log_activity, save_visit

router = APIRouter(prefix="/api")


class BookingIn(BaseModel):
    name: str
    dob: str = ""
    reason: str = ""
    symptoms: dict = {}
    transcript_prefill: str = ""
    plan_prefill: str = ""


class VisitUpdate(BaseModel):
    transcript: str | None = None
    physician_plan: str | None = None


@router.post("/booking")
def api_create_booking(booking: BookingIn):
    visit = create_visit(booking.model_dump())
    log_activity("patient", f"booked visit: {booking.reason}", visit_id=visit["id"])
    visit = generate_intake(visit)
    return visit


@router.get("/visits")
def api_list_visits():
    visits = list_visits()
    return [
        {
            "id": v["id"],
            "patient_name": v["patient"].get("name"),
            "reason": v["booking"].get("reason"),
            "status": v["status"],
            "needs_manual_review": v.get("needs_manual_review", False),
        }
        for v in visits
    ]


@router.get("/visits/{visit_id}")
def api_get_visit(visit_id: str):
    visit = get_visit(visit_id)
    if not visit:
        raise HTTPException(status_code=404, detail="Visit not found")
    return visit


@router.patch("/visits/{visit_id}")
def api_update_visit(visit_id: str, update: VisitUpdate):
    visit = get_visit(visit_id)
    if not visit:
        raise HTTPException(status_code=404, detail="Visit not found")
    if update.transcript is not None:
        visit["transcript"] = update.transcript
    if update.physician_plan is not None:
        visit["physician_plan"] = update.physician_plan
    save_visit(visit)
    return visit


@router.post("/visits/{visit_id}/approve")
def api_approve_visit(visit_id: str):
    visit = get_visit(visit_id)
    if not visit:
        raise HTTPException(status_code=404, detail="Visit not found")
    log_activity("physician", "approved transcript/plan, running document pipeline", visit_id=visit_id)
    return approve_visit(visit)
