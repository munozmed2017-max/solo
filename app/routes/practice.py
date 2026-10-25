import io

import qrcode
import requests
from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.storage import get_earnings, get_practice, log_activity, save_practice

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


@router.get("/earnings")
def api_earnings():
    return get_earnings()


@router.get("/qr")
def api_qr(url: str):
    img = qrcode.make(url, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


@router.get("/ngrok-url")
def api_ngrok_url():
    """Reads ngrok's local status API (127.0.0.1:4040), which only exists
    while an ngrok process is running - not a guess, the actual current
    tunnel. Returns {"url": null} if ngrok isn't running."""
    try:
        resp = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=1)
        tunnels = resp.json().get("tunnels", [])
        https_urls = [t["public_url"] for t in tunnels if t["public_url"].startswith("https://")]
        return {"url": https_urls[0] if https_urls else None}
    except Exception:
        return {"url": None}
