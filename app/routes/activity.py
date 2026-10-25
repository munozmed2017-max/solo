from fastapi import APIRouter

from app.storage import list_activity

router = APIRouter(prefix="/api")


@router.get("/activity")
def api_activity(limit: int = 200):
    return list_activity(limit)
