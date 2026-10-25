from fastapi import APIRouter

from app.results import start_batch_background
from app.storage import get_results_run, log_activity

router = APIRouter(prefix="/api")


@router.get("/results")
def api_get_results():
    return get_results_run() or {"status": "never_run"}


@router.post("/results/run")
def api_run_results():
    log_activity("results batch", "started 10-case x 3-method comparison run")
    start_batch_background()
    return {"status": "started"}
