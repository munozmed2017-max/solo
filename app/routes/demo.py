from fastapi import APIRouter
from pydantic import BaseModel

from app.storage import get_flags, reset_demo, set_flag

router = APIRouter(prefix="/api")


class FlagUpdate(BaseModel):
    value: bool


@router.get("/demo/flags")
def api_get_flags():
    return get_flags()


@router.post("/demo/flags/{key}")
def api_set_flag(key: str, update: FlagUpdate):
    return set_flag(key, update.value)


@router.post("/demo/reset")
def api_reset_demo():
    return reset_demo()
