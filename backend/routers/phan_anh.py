"""API phản ánh ô nhiễm từ người dân (xem services/phan_anh.py)."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core import config  # noqa: F401
import models
from auth import decode_access_token
from core import logbus, ratelimit
from core.config import COOKIE_NAME
from core.security import get_current_user, ip_cua, require_admin
from database import SessionLocal
from services import phan_anh as pa

router = APIRouter(tags=["Phản ánh ô nhiễm"])


class PhanAnhMoi(BaseModel):
    loai: str = Field(max_length=30)
    mo_ta: str | None = Field(None, max_length=2000)   # giới hạn thật (500) kiểm ở services để báo lỗi tiếng Việt
    vi_do: float
    kinh_do: float


class Duyet(BaseModel):
    trang_thai: str = Field(max_length=12)


def _nguoi_xem(request: Request) -> int | None:
    """ID người đang đăng nhập (nếu có) — để đánh dấu phản ánh của mình / đã bấm 'Tôi cũng thấy'. Không bắt buộc."""
    p = decode_access_token(request.cookies.get(COOKIE_NAME) or "", loai="phien")
    if not p:
        return None
    with SessionLocal() as db:
        u = db.query(models.NguoiDung.id).filter(models.NguoiDung.email == p.get("sub")).first()
        return u.id if u else None


@router.get("/api/v1/phan-anh/loai")
def ds_loai():
    return {"loai": [{"ma": k, **v} for k, v in pa.LOAI.items()], "mo_ta_toi_da": pa.MO_TA_TOI_DA,
            "pham_vi": {"vi_do": pa.VI_DO, "kinh_do": pa.KINH_DO}}


@router.get("/api/v1/phan-anh")
def ds_phan_anh(request: Request, gio: int = pa.GIO_HIEN_MAC_DINH):
    """Phản ánh trong `gio` giờ gần nhất (mặc định 72, tối đa 168) để vẽ lên bản đồ. Không cần đăng nhập."""
    return {"gio": max(1, min(gio, pa.GIO_HIEN_TOI_DA)), "phan_anh": pa.ds_cong_khai(gio, _nguoi_xem(request)), "thong_ke": pa.thong_ke(30)}


@router.post("/api/v1/phan-anh")
def gui_phan_anh(body: PhanAnhMoi, request: Request, user: models.NguoiDung = Depends(get_current_user)):
    try:
        du_lieu = pa.chuan_hoa(body.loai, body.mo_ta, body.vi_do, body.kinh_do)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    cho = ratelimit.vuot_gioi_han("phan_anh", f"u{user.id}", toi_da=5, cua_so_giay=3600)
    if cho:
        raise HTTPException(429, f"Bạn đã gửi 5 phản ánh trong 1 giờ. Vui lòng thử lại sau {(cho + 59) // 60} phút")
    ma = pa.them(user.id, du_lieu)
    logbus.ghi("INFO", "phan_anh", "gui", f"Phản ánh #{ma}: {pa.LOAI[du_lieu['loai']]['ten']} tại ({du_lieu['vi_do']}, {du_lieu['kinh_do']})",
               nguoi_dung=user.email, ip=ip_cua(request))
    return {"id": ma, "message": "Đã ghi nhận phản ánh. Phần mô tả sẽ hiển thị công khai sau khi quản trị viên xác minh."}


@router.get("/api/v1/phan-anh/cua-toi")
def cua_toi(user: models.NguoiDung = Depends(get_current_user)):
    return {"phan_anh": pa.ds_cua_toi(user.id)}


@router.post("/api/v1/phan-anh/{ma}/xac-nhan")
def toi_cung_thay(ma: int, user: models.NguoiDung = Depends(get_current_user)):
    if ratelimit.vuot_gioi_han("phan_anh_xn", f"u{user.id}", toi_da=30, cua_so_giay=3600):
        raise HTTPException(429, "Thao tác quá nhiều lần, vui lòng thử lại sau")
    kq = pa.xac_nhan(ma, user.id)
    if kq == "khong_co":
        raise HTTPException(404, "Không tìm thấy phản ánh")
    if kq == "cua_minh":
        raise HTTPException(400, "Bạn không thể tự xác nhận phản ánh của mình")
    return {"message": "Đã ghi nhận: bạn cũng thấy hiện tượng này" if kq == "ok" else "Bạn đã xác nhận phản ánh này rồi"}


@router.delete("/api/v1/phan-anh/{ma}")
def xoa_phan_anh(ma: int, request: Request, user: models.NguoiDung = Depends(get_current_user)):
    if not pa.xoa(ma, user.id, user.vai_tro == "admin"):
        raise HTTPException(404, "Không tìm thấy phản ánh của bạn")
    logbus.ghi("INFO", "phan_anh", "xoa", f"Xóa phản ánh #{ma}", nguoi_dung=user.email, ip=ip_cua(request))
    return {"message": "Đã xóa phản ánh"}


@router.get("/api/v1/admin/phan-anh")
def quan_tri_ds(admin: models.NguoiDung = Depends(require_admin)):
    return {"phan_anh": pa.ds_quan_tri(30)}


@router.post("/api/v1/admin/phan-anh/{ma}/duyet")
def quan_tri_duyet(ma: int, body: Duyet, request: Request, admin: models.NguoiDung = Depends(require_admin)):
    try:
        ok = pa.duyet(ma, body.trang_thai, admin.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if not ok:
        raise HTTPException(404, "Không tìm thấy phản ánh")
    logbus.ghi("INFO", "phan_anh", "duyet", f"Phản ánh #{ma} → {body.trang_thai}", nguoi_dung=admin.email, ip=ip_cua(request))
    return {"message": {"xac_minh": "Đã xác minh, mô tả hiển thị công khai", "an": "Đã ẩn khỏi bản đồ", "moi": "Đã chuyển về chưa xác minh"}[body.trang_thai]}
