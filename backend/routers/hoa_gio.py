"""API hoa gió / hoa gió ô nhiễm (GET /api/v1/hoa-gio) và bảng ngưỡng tham chiếu (GET /api/v1/nguong)."""

from core import config  # noqa: F401
from core.nguong import bang_nguong
from fastapi import APIRouter, HTTPException, Query

from services import hoa_gio as hg

router = APIRouter()


@router.get("/api/v1/hoa-gio")
def lay_hoa_gio(so_ngay: int = Query(90, ge=7, le=730), nguong: float = Query(25.0, gt=0, le=500),
                so_huong: int = Query(8), lat: float = Query(hg.TAM_TP[0], ge=10.2, le=11.6),
                lon: float = Query(hg.TAM_TP[1], ge=106.2, le=107.6)):
    """Hoa gió (tần suất theo hướng, theo lớp tốc độ, gió lặng) và hoa gió ô nhiễm: PM2.5 trung bình và
    xác suất PM2.5 theo giờ vượt `nguong` (µg/m³) khi gió thổi từ từng hướng; CBPF theo hướng × tốc độ."""
    if so_huong not in (8, 16):
        raise HTTPException(422, "so_huong chỉ nhận 8 hoặc 16")
    try:
        return hg.hoa_gio(so_ngay, nguong, so_huong, lat, lon)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:  # lỗi mạng tới Open-Meteo
        raise HTTPException(503, f"Không lấy được số liệu gió/PM2.5 từ Open-Meteo: {type(e).__name__}")


@router.get("/api/v1/nguong")
def lay_nguong(ngay: str | None = None):
    """Ngưỡng QCVN 05:2023/BTNMT và WHO 2021 áp dụng tại một ngày (mặc định hôm nay)."""
    return bang_nguong(ngay)
