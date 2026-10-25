from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agents.agent_builder import poll_build, start_build
from app.storage import get_tool, list_tools, log_activity
from app.tool_runner import draft_a1c_reminder, run_diabetes_tracker

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


@router.post("/tools/{tool_id}/run")
def api_run_tool(tool_id: str):
    tool = get_tool(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="tool not found")
    if "diabetes" in tool["description"].lower():
        log_activity("agent builder", "ran diabetes tracker tool", visit_id=None)
        return {"type": "diabetes_tracker", **run_diabetes_tracker()}
    return {"type": "unsupported", "message": "Running this tool type isn't wired up yet."}


@router.post("/tools/{tool_id}/draft-reminder")
def api_draft_reminder(tool_id: str):
    tool = get_tool(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="tool not found")
    data = run_diabetes_tracker()
    return draft_a1c_reminder(data["overdue_count"])
