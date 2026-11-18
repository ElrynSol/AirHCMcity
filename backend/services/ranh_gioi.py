"""Truy vấn không gian PostGIS trên ranh giới phường/xã (bảng phuong_xa, nạp bởi data_pipeline/nap_ranh_gioi.py).

Các phép toán không gian làm NGAY TRONG CSDL (có chỉ mục GiST), không tải hình học về Python:
- ST_PointOnSurface: điểm đại diện luôn nằm TRONG phường (khác tâm hình học có thể rơi ra ngoài phường hình chữ C).
- Toán tử KNN `<->` + ST_Distance(geography): điểm ước tính gần nhất và khoảng cách thật (mét) trên mặt cầu.
- ST_Contains: điểm (điểm ước tính, phản ánh) thuộc phường nào.
- ST_Union + ST_SimplifyPreserveTopology: đường bao toàn thành phố để cắt bản đồ nhiệt.
- ST_AsGeoJSON: xuất hình học cho Leaflet.
"""

from __future__ import annotations

import json
import time

from sqlalchemy import text

from database import engine

TTL = 3600
_dem: dict = {}
MA_CON_DAO = "26732"   # đặc khu Côn Đảo cách đất liền ~180 km, không có trạm: loại khỏi khung bản đồ nhiệt


def _nho(khoa, ham):
    if khoa in _dem and time.time() - _dem[khoa][0] < TTL:
        return _dem[khoa][1]
    v = ham()
    _dem[khoa] = (time.time(), v)
    return v


def xoa_bo_nho():
    _dem.clear()


def co_du_lieu() -> bool:
    try:
        with engine.connect() as c:
            return c.execute(text("SELECT EXISTS (SELECT 1 FROM phuong_xa)")).scalar()
    except Exception:
        return False


def do_tin_cay_theo_km(km: float | None) -> str:
    if km is None:
        return "khong_ro"
    return "cao" if km <= 5 else "trung_binh" if km <= 15 else "thap"


def ds_phuong() -> list[dict]:
    """Mỗi phường: điểm đại diện, trạm gần nhất (KNN) và khoảng cách thật tới trạm đó."""
    def lay():
        with engine.connect() as c:
            rows = c.execute(text("""
                WITH d AS (SELECT ma, ten, ten_day_du, loai, khu_vuc, dien_tich_km2, ST_PointOnSurface(geom) AS c FROM phuong_xa)
                SELECT d.ma, d.ten, d.ten_day_du, d.loai, d.khu_vuc, d.dien_tich_km2, ST_Y(d.c) AS lat, ST_X(d.c) AS lon,
                       g.ma_tram, g.km
                FROM d LEFT JOIN LATERAL (
                    SELECT t.ma_tram, ST_Distance(d.c::geography, t.toado::geography) / 1000.0 AS km
                    FROM tram_quan_trac t WHERE t.toado IS NOT NULL
                    ORDER BY t.toado <-> d.c LIMIT 1) g ON TRUE
                ORDER BY d.ma
            """)).fetchall()
        return [{"ma": r.ma, "ten": r.ten, "ten_day_du": r.ten_day_du, "loai": r.loai, "khu_vuc": r.khu_vuc,
                 "dien_tich_km2": r.dien_tich_km2, "lat": r.lat, "lon": r.lon, "tram_gan_nhat": r.ma_tram,
                 "km_tram_gan_nhat": round(r.km, 1) if r.km is not None else None,
                 "do_tin_cay": do_tin_cay_theo_km(r.km)} for r in rows]
    return _nho("ds_phuong", lay)


def khung_ban_do() -> dict | None:
    """Khung chữ nhật bao đất liền TP.HCM (bỏ Côn Đảo) để dựng lưới nội suy."""
    def lay():
        with engine.connect() as c:
            r = c.execute(text("SELECT ST_XMin(e) x0, ST_YMin(e) y0, ST_XMax(e) x1, ST_YMax(e) y1 FROM "
                               "(SELECT ST_Extent(geom) e FROM phuong_xa WHERE ma <> :cd) k"), {"cd": MA_CON_DAO}).fetchone()
        return None if r is None or r.x0 is None else {"lon0": r.x0, "lat0": r.y0, "lon1": r.x1, "lat1": r.y1}
    return _nho("khung", lay)


def duong_bao_thanh_pho(bo_con_dao: bool = True) -> dict | None:
    """Đường bao toàn thành phố (hợp các phường, đơn giản hóa ~200 m) dạng GeoJSON."""
    def lay():
        with engine.connect() as c:
            g = c.execute(text("SELECT ST_AsGeoJSON(ST_SimplifyPreserveTopology(ST_Union(geom), 0.002), 5) FROM phuong_xa "
                               "WHERE (:bo = FALSE OR ma <> :cd)"), {"bo": bo_con_dao, "cd": MA_CON_DAO}).scalar()
        return json.loads(g) if g else None
    return _nho(("bao", bo_con_dao), lay)


def geojson_phuong() -> dict:
    """Toàn bộ phường/xã dạng FeatureCollection (cho bản đồ choropleth)."""
    def lay():
        with engine.connect() as c:
            rows = c.execute(text("SELECT ma, ten_day_du, khu_vuc, ST_AsGeoJSON(geom, 5) g FROM phuong_xa ORDER BY ma")).fetchall()
        return {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": json.loads(r.g), "properties": {"ma": r.ma, "ten": r.ten_day_du, "khu_vuc": r.khu_vuc}}
            for r in rows]}
    return _nho("geojson", lay)


def phuong_chua_diem(lat: float, lon: float) -> dict | None:
    """Điểm (lat, lon) thuộc phường/xã nào (ST_Contains, dùng chỉ mục GiST)."""
    with engine.connect() as c:
        r = c.execute(text("SELECT ma, ten_day_du, khu_vuc FROM phuong_xa WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)) LIMIT 1"),
                      {"lat": lat, "lon": lon}).fetchone()
    return {"ma": r.ma, "ten": r.ten_day_du, "khu_vuc": r.khu_vuc} if r else None
