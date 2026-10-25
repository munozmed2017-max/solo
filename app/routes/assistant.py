from fastapi import APIRouter
from pydantic import BaseModel

from app.assistant import ask

router = APIRouter(prefix="/api")


class AssistantQuery(BaseModel):
    query: str


@router.post("/assistant/ask")
def api_assistant_ask(req: AssistantQuery):
    return ask(req.query)
