"""Kiểm tra sức khỏe hệ thống (không cần đăng nhập, không lộ dữ liệu nhạy cảm)."""

from core import config  # noqa: F401
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from database import engine
from core import events
from services import cdc

router = APIRouter()


@router.get("/api/v1/health")
def health():
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    bus = events.thong_ke()
    # Mất CSDL → 503 để Docker/giám sát uptime nhận ra máy chủ không khỏe và tự khởi động lại
    return JSONResponse({"trang_thai": "ok" if db_ok else "loi", "csdl": db_ok,
                         "cdc_dang_nghe": cdc.dang_nghe, "su_kien_cho_xu_ly": bus["cho_xu_ly"]},
                        status_code=200 if db_ok else 503)
