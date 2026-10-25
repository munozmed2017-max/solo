from fastapi import APIRouter
from pydantic import BaseModel

from app.agents.agent_builder import run as agent_builder_run
from app.storage import list_tools, log_activity

router = APIRouter(prefix="/api")


class ToolRequest(BaseModel):
    description: str


@router.get("/tools")
def api_list_tools():
    return list_tools()


@router.post("/tools/build")
def api_build_tool(req: ToolRequest):
    log_activity("agent builder", "building and testing a new tool via Antigravity", detail=req.description)
    tool = agent_builder_run(req.description)
    log_activity(
        "agent builder",
        "tool build finished",
        detail=f"tests_passed={tool['tests_passed']} final_count={tool['final_count']}",
    )
    return tool
