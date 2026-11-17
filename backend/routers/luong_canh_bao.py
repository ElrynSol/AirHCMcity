"""Trình diễn luồng cảnh báo từng giai đoạn và Hộp thư đã gửi (chỉ admin)."""

from core import config  # noqa: F401
from database import get_db
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
import models
from core.security import require_admin
from services.canh_bao_service import chay_demo

router = APIRouter()


@router.post("/api/v1/admin/demo-canh-bao")
def demo_canh_bao(payload: dict, admin: models.NguoiDung = Depends(require_admin)):
    try:
        tram_id = int(payload.get("tram_id"))
        nguong = int(payload.get("nguong_thu", 100))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Trạm hoặc ngưỡng không hợp lệ")
    if not 0 <= nguong <= 500:
        raise HTTPException(status_code=400, detail="Ngưỡng thử phải từ 0 đến 500")
    return chay_demo(tram_id, nguong, bool(payload.get("gui_that")), admin.email)


@router.get("/api/v1/admin/thu-da-gui")
def ds_thu_da_gui(limit: int = 50, admin: models.NguoiDung = Depends(require_admin), db: Session = Depends(get_db)):
    limit = max(1, min(limit, 200))
    rows = db.execute(text("""
        SELECT id, thoi_gian, email, ma_tram, aqi, tieu_de, noi_dung, trang_thai, loai
        FROM thu_da_gui ORDER BY id DESC LIMIT :l
    """), {"l": limit}).fetchall()
    return [{"id": r.id, "thoi_gian": r.thoi_gian.strftime("%Y-%m-%d %H:%M:%S"), "email": r.email, "ma_tram": r.ma_tram,
             "aqi": r.aqi, "tieu_de": r.tieu_de, "noi_dung": r.noi_dung, "trang_thai": r.trang_thai, "loai": r.loai} for r in rows]
