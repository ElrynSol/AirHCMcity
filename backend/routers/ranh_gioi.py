"""API ranh giới hành chính từ PostGIS: phường/xã (GeoJSON), đường bao thành phố, tra cứu điểm thuộc phường nào."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from core import config  # noqa: F401
from services import ranh_gioi as rg

router = APIRouter(prefix="/api/v1/ranh-gioi", tags=["Ranh giới (PostGIS)"])
_LUU = {"Cache-Control": "public, max-age=86400"}   # ranh giới hầu như không đổi: trình duyệt giữ 1 ngày


def _can_du_lieu():
    if not rg.co_du_lieu():
        raise HTTPException(503, "Chưa nạp ranh giới phường/xã. Chạy: python data_pipeline/nap_ranh_gioi.py")


@router.get("/phuong-xa")
def phuong_xa_geojson():
    _can_du_lieu()
    return JSONResponse(rg.geojson_phuong(), headers=_LUU)


@router.get("/phuong-xa/danh-sach")
def phuong_xa_danh_sach():
    """Danh sách phường kèm trạm gần nhất (KNN) và khoảng cách — không có hình học."""
    _can_du_lieu()
    return JSONResponse({"phuong": rg.ds_phuong()}, headers=_LUU)


@router.get("/thanh-pho")
def thanh_pho():
    _can_du_lieu()
    return JSONResponse({"type": "Feature", "geometry": rg.duong_bao_thanh_pho(False), "properties": {"ten": "TP. Hồ Chí Minh"}}, headers=_LUU)


@router.get("/tra-cuu")
def tra_cuu(lat: float, lon: float):
    _can_du_lieu()
    return {"phuong": rg.phuong_chua_diem(lat, lon)}
