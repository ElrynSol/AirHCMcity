"""API tra cứu không gian: quét vùng (PostGIS), trạm gần nhất (KNN), chỉ đường (OSRM) — xem services/khong_gian.py."""

import time

import requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core import config  # noqa: F401
from core import logbus, ratelimit
from core.security import ip_cua
from services import khong_gian as kg

router = APIRouter(prefix="/api/v1/khong-gian", tags=["Tra cứu không gian"])
OSRM = "https://router.project-osrm.org/route/v1"   # máy chủ định tuyến OSRM công cộng (dữ liệu OpenStreetMap)
_dem_duong: dict = {}


class YeuCauQuet(BaseModel):
    kieu: str = Field(max_length=10)                 # tron | khung | da_giac
    tam: dict | None = None                          # {lat, lon} cho vòng tròn
    ban_kinh_m: float | None = None
    dinh: list[dict] | None = Field(None, max_length=kg.SO_DINH_MAX)   # [{lat, lon}] cho khung / đa giác
    cot_moc: dict | None = None                      # vị trí người dùng để đo khoảng cách
    tu_sua: bool = False                             # tự sửa đa giác tự cắt bằng ST_MakeValid


@router.post("/quet")
def quet(yc: YeuCauQuet, request: Request):
    if ratelimit.vuot_gioi_han("kg_quet", ip_cua(request), toi_da=120, cua_so_giay=60):
        raise HTTPException(429, "Quét quá nhanh, vui lòng chậm lại")
    try:
        return kg.quet(yc.model_dump())
    except kg.LoiHinhHoc as exc:
        return JSONResponse({"detail": str(exc), "xung_dot": exc.chi_tiet}, status_code=422)


@router.get("/tram-gan-nhat")
def tram_gan_nhat(lat: float, lon: float, so: int = 3):
    try:
        return {"tram": kg.tram_gan_nhat(lat, lon, max(1, min(so, 10)))}
    except kg.LoiHinhHoc as exc:
        raise HTTPException(422, str(exc))


@router.get("/duong-di")
def duong_di(tu_lat: float, tu_lon: float, den_lat: float, den_lon: float, phuong_tien: str = "driving", request: Request = None):
    """Chỉ đường bằng OSRM (OpenStreetMap). OSRM lỗi/không phản hồi thì trả khoảng cách đường chim bay (PostGIS)."""
    try:
        kg._diem_hop_le(tu_lat, tu_lon, "Điểm đi"); kg._diem_hop_le(den_lat, den_lon, "Điểm đến")
    except kg.LoiHinhHoc as exc:
        raise HTTPException(422, str(exc))
    if phuong_tien not in ("driving", "foot", "bike"):
        phuong_tien = "driving"
    if request is not None and ratelimit.vuot_gioi_han("kg_duong", ip_cua(request), toi_da=30, cua_so_giay=60):
        raise HTTPException(429, "Yêu cầu chỉ đường quá nhanh, vui lòng chậm lại")
    khoa = tuple(round(x, 4) for x in (tu_lat, tu_lon, den_lat, den_lon)) + (phuong_tien,)
    if khoa in _dem_duong and time.time() - _dem_duong[khoa][0] < 600:
        return _dem_duong[khoa][1]
    google = (f"https://www.google.com/maps/dir/?api=1&origin={tu_lat},{tu_lon}&destination={den_lat},{den_lon}"
              f"&travelmode={'walking' if phuong_tien == 'foot' else 'bicycling' if phuong_tien == 'bike' else 'driving'}")
    try:
        r = requests.get(f"{OSRM}/{phuong_tien}/{tu_lon},{tu_lat};{den_lon},{den_lat}",
                         params={"overview": "full", "geometries": "geojson"}, timeout=8,
                         headers={"User-Agent": "AirHCM-do-an/1.0"})
        d = r.json()
        if d.get("code") != "Ok" or not d.get("routes"):
            raise ValueError(d.get("message") or d.get("code"))
        tuyen = d["routes"][0]
        kq = {"nguon": "osrm", "km": round(tuyen["distance"] / 1000, 2), "phut": round(tuyen["duration"] / 60, 1),
              "geojson": tuyen["geometry"], "google_maps": google}
    except Exception as exc:
        logbus.ghi("WARN", "khong_gian", "osrm_loi", f"{type(exc).__name__}: {str(exc)[:150]}")
        from sqlalchemy import text
        from database import engine
        with engine.connect() as c:
            m = c.execute(text("SELECT ST_Distance(ST_SetSRID(ST_MakePoint(:a, :b), 4326)::geography, "
                               "ST_SetSRID(ST_MakePoint(:c, :d), 4326)::geography)"),
                          {"a": tu_lon, "b": tu_lat, "c": den_lon, "d": den_lat}).scalar()
        kq = {"nguon": "chim_bay", "km": round(m / 1000, 2), "phut": None,
              "geojson": {"type": "LineString", "coordinates": [[tu_lon, tu_lat], [den_lon, den_lat]]}, "google_maps": google,
              "ghi_chu": "Máy chủ chỉ đường OSRM không phản hồi — hiển thị khoảng cách đường chim bay (PostGIS)."}
    _dem_duong[khoa] = (time.time(), kq)
    return kq
