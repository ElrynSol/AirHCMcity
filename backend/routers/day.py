"""API thông báo đẩy (Web Push) và AQI hiện tại dạng gọn cho tác vụ nền của app Android."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core import config  # noqa: F401
from core import ratelimit
from core.security import ip_cua, thiet_bi_cua
from services import day_thong_bao as day

router = APIRouter(prefix="/api/v1/day", tags=["Thông báo đẩy"])


class DangKy(BaseModel):
    dang_ky: dict                        # PushSubscription.toJSON() của trình duyệt
    nguong: int = Field(101, ge=51, le=301)   # mặc định: từ mức "Kém" (AQI 101) trở lên
    cu: str | None = Field(None, max_length=2000)


class Endpoint(BaseModel):
    endpoint: str = Field(max_length=2000)


def _nguoi_dung_id(request: Request) -> int | None:
    """Gắn đăng ký với tài khoản nếu đang đăng nhập (không bắt buộc)."""
    from auth import decode_access_token
    from core.config import COOKIE_NAME
    from database import SessionLocal
    import models
    p = decode_access_token(request.cookies.get(COOKIE_NAME) or "", loai="phien")
    if not p:
        return None
    with SessionLocal() as db:
        u = db.query(models.NguoiDung.id).filter(models.NguoiDung.email == p.get("sub")).first()
        return u.id if u else None


@router.get("/khoa-cong-khai")
def khoa_cong_khai():
    return {"khoa": day.khoa_cong_khai()}


@router.post("/dang-ky")
def dang_ky(body: DangKy, request: Request):
    cho = ratelimit.vuot_gioi_han("day_dk", ip_cua(request), toi_da=30, cua_so_giay=3600)
    if cho:
        raise HTTPException(429, "Thao tác quá nhiều lần, vui lòng thử lại sau")
    try:
        day.luu_dang_ky(body.dang_ky, body.nguong, _nguoi_dung_id(request), thiet_bi_cua(request), body.cu)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"message": f"Đã bật thông báo nền khi AQI ≥ {body.nguong}"}


@router.post("/huy")
def huy(body: Endpoint):
    day.huy_dang_ky(body.endpoint)
    return {"message": "Đã tắt thông báo nền trên thiết bị này"}


@router.post("/trang-thai")
def trang_thai(body: Endpoint):
    return {"dang_ky": day.trang_thai(body.endpoint)}


@router.post("/thu")
def gui_thu(body: Endpoint, request: Request):
    cho = ratelimit.vuot_gioi_han("day_thu", ip_cua(request), toi_da=5, cua_so_giay=600)
    if cho:
        raise HTTPException(429, "Gửi thử quá nhiều lần, vui lòng đợi vài phút")
    kq = day.gui_thu(body.endpoint)
    if kq != "ok":
        raise HTTPException(400, kq)
    return {"message": "Đã gửi thông báo thử"}


@router.get("/aqi-hien-tai")
def aqi_hien_tai():
    """AQI TP.HCM hiện tại, gói nhỏ (~200 byte) cho tác vụ nền của app gọi mỗi 30 phút."""
    from services.tong_quan import tong_quan
    v = tong_quan() or {}
    h = v.get("hien_tai") or {}
    return {"aqi": h.get("aqi"), "muc": h.get("muc"), "chat": h.get("chat"), "pm25": h.get("pm25"),
            "khuyen_nghi": h.get("nhom_nhay_cam") or h.get("nguoi_binh_thuong"), "cap_nhat": v.get("cap_nhat")}
