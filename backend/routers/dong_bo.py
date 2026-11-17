"""API đồng bộ dữ liệu tự động: trạng thái (công khai), chạy ngay và xem log (chỉ admin)."""

from core import config  # noqa: F401
from fastapi import APIRouter, Depends

import models
from core import logbus
from core.security import require_admin
from services import dong_bo

router = APIRouter()


@router.get("/api/v1/dong-bo/trang-thai")
def trang_thai():
    return dong_bo.trang_thai()


@router.post("/api/v1/admin/dong-bo")
def dong_bo_ngay(admin: models.NguoiDung = Depends(require_admin)):
    ok = dong_bo.chay_ngay("admin")
    if ok:
        logbus.ghi("INFO", "dong_bo", "admin_kich_hoat", "Admin bấm Đồng bộ ngay", nguoi_dung=admin.email)
    return {"da_bat_dau": ok, "thong_bao": "Đã bắt đầu đồng bộ, thường mất 2–5 phút." if ok else "Đang có một lần đồng bộ chạy."}


@router.get("/api/v1/admin/dong-bo/log")
def xem_log(dong: int = 80, admin: models.NguoiDung = Depends(require_admin)):
    return {"log": dong_bo.doc_log(max(10, min(dong, 400)))}
