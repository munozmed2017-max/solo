import io

import qrcode
from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.storage import get_practice, log_activity, save_practice

router = APIRouter(prefix="/api")


class PracticeUpdate(BaseModel):
    name: str
    physician_name: str
    hours: str
    visit_fee: str


@router.get("/practice")
def api_get_practice():
    return get_practice()


@router.post("/practice")
def api_save_practice(update: PracticeUpdate):
    practice = get_practice()
    practice.update(update.model_dump())
    save_practice(practice)
    log_activity("physician", "updated practice settings")
    return practice


@router.get("/qr")
def api_qr(url: str):
    img = qrcode.make(url, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")
