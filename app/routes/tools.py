from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agents.agent_builder import poll_build, start_build
from app.storage import list_tools, log_activity

router = APIRouter(prefix="/api")


class ToolRequest(BaseModel):
    description: str


@router.get("/tools")
def api_list_tools():
    return list_tools()


@router.post("/tools/build/start")
def api_start_build(req: ToolRequest):
    log_activity("agent builder", "building and testing a new tool via Antigravity", detail=req.description)
    return start_build(req.description)


@router.get("/tools/{tool_id}/status")
def api_poll_build(tool_id: str):
    try:
        return poll_build(tool_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
