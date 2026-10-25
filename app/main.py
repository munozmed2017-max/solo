from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.models import call_model
from app.routes.activity import router as activity_router
from app.routes.approvals import router as approvals_router
from app.routes.demo import router as demo_router
from app.routes.visits import router as visits_router
from app.storage import ensure_panel_seeded

ROOT = Path(__file__).resolve().parent.parent

app = FastAPI(title="Solo")

app.include_router(visits_router)
app.include_router(approvals_router)
app.include_router(activity_router)
app.include_router(demo_router)


@app.on_event("startup")
def startup():
    ensure_panel_seeded()


@app.get("/test-argon")
def test_argon():
    interaction = call_model(
        "orchestrator",
        "Reply with exactly one word: ready",
        thinking_level="low",
    )
    return {"model": "gemini-4-argon", "output": interaction.output_text}


app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
