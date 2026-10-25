from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.storage import list_approval_items, log_activity, mark_document_sent, set_document_approval

router = APIRouter(prefix="/api")


class ApprovalDecision(BaseModel):
    status: str  # "approved" | "rejected"
    edited_text: str | None = None
    comment: str = ""


@router.get("/approvals")
def api_list_approvals():
    return list_approval_items()


@router.post("/visits/{visit_id}/documents/{doc_type}/decision")
def api_decide(visit_id: str, doc_type: str, decision: ApprovalDecision):
    try:
        visit = set_document_approval(visit_id, doc_type, decision.status, decision.edited_text, decision.comment)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    log_activity("physician", f"{decision.status} {doc_type}", visit_id=visit_id)
    return visit


@router.post("/visits/{visit_id}/documents/{doc_type}/send")
def api_send(visit_id: str, doc_type: str):
    try:
        visit = mark_document_sent(visit_id, doc_type)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    log_activity("system", f"sent {doc_type} (simulated)", visit_id=visit_id)
    return visit
