"""API trang Tổng quan: gom AQI hiện tại, so sánh ngưỡng, thời tiết, dự báo 24 giờ, xu hướng, xếp hạng điểm ước tính."""

from core import config  # noqa: F401
from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from services.tong_quan import tong_quan

router = APIRouter()


@router.get("/api/v1/tong-quan")
def get_tong_quan():
    return tong_quan()


@router.get("/", include_in_schema=False)
def trang_chu():
    """Trang chủ là Tổng quan; bản đồ vẫn ở /index.html (app Android mở thẳng /index.html)."""
    return RedirectResponse("/tong-quan.html", status_code=301)   # 301: máy tìm kiếm chuyển thứ hạng sang trang đích
