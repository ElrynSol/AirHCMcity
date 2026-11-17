"""Đăng ký/hủy cảnh báo email, kích hoạt gửi thủ công (admin)."""

from core import config  # noqa: F401  (nạp .env và đường dẫn dự án trước)
from database import get_db
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
import models
from fastapi import APIRouter
from core.security import get_current_user, require_admin
from services.canh_bao_service import chay_gui_canh_bao
from core import logbus

router = APIRouter()


@router.get("/api/v1/canh-bao/dang-ky")
def ds_dang_ky_canh_bao(current_user: models.NguoiDung = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT d.id, d.tram_id, d.nguong_aqi, d.hoat_dong, d.lan_gui_cuoi, t.ma_tram, t.ten_tram
        FROM dang_ky_canh_bao d JOIN tram_quan_trac t ON t.id = d.tram_id
        WHERE d.email = :email ORDER BY d.id
    """), {"email": current_user.email}).fetchall()
    return [{"id": r.id, "tram_id": r.tram_id, "ma_tram": r.ma_tram, "ten_tram": r.ten_tram,
             "nguong_aqi": r.nguong_aqi, "hoat_dong": r.hoat_dong,
             "lan_gui_cuoi": str(r.lan_gui_cuoi) if r.lan_gui_cuoi else None} for r in rows]


@router.post("/api/v1/canh-bao/dang-ky")
def them_dang_ky_canh_bao(payload: dict, current_user: models.NguoiDung = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        tram_id = int(payload.get("tram_id"))
        nguong = int(payload.get("nguong_aqi", 100))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Trạm hoặc ngưỡng không hợp lệ")
    if not 25 <= nguong <= 400:
        raise HTTPException(status_code=400, detail="Ngưỡng AQI phải từ 25 đến 400")
    if not db.query(models.TramQuanTrac).filter(models.TramQuanTrac.id == tram_id).first():
        raise HTTPException(status_code=404, detail="Không tìm thấy trạm")
    db.execute(text("""
        INSERT INTO dang_ky_canh_bao (email, tram_id, nguong_aqi) VALUES (:e, :t, :n)
        ON CONFLICT (email, tram_id) DO UPDATE SET nguong_aqi = :n, hoat_dong = TRUE, lan_gui_cuoi = NULL
    """), {"e": current_user.email, "t": tram_id, "n": nguong})
    db.commit()
    logbus.ghi("INFO", "canh_bao", "dang_ky", f"Đăng ký cảnh báo trạm {tram_id}, ngưỡng {nguong}", nguoi_dung=current_user.email)
    # Đánh giá ngay trạm vừa đăng ký (nền), không phải chờ dữ liệu mới hay vòng quét 6 giờ
    import threading
    from services.canh_bao_service import danh_gia_canh_bao
    threading.Thread(target=lambda: danh_gia_canh_bao([tram_id]), daemon=True).start()
    return {"message": "Đã lưu đăng ký cảnh báo. Hệ thống gửi tối đa 1 email/ngày cho mỗi trạm khi AQI đạt hoặc vượt ngưỡng."}


@router.delete("/api/v1/canh-bao/dang-ky/{dk_id}")
def xoa_dang_ky_canh_bao(dk_id: int, current_user: models.NguoiDung = Depends(get_current_user), db: Session = Depends(get_db)):
    r = db.execute(text("DELETE FROM dang_ky_canh_bao WHERE id = :id AND email = :e"), {"id": dk_id, "e": current_user.email})
    db.commit()
    if r.rowcount == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy đăng ký")
    return {"message": "Đã hủy đăng ký"}


@router.post("/api/v1/admin/gui-canh-bao")
def admin_gui_canh_bao(admin: models.NguoiDung = Depends(require_admin)):
    return chay_gui_canh_bao()
