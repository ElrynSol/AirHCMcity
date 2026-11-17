"""AQI theo trạm, toàn bộ trạm và theo ngày."""

from core import config  # noqa: F401  (nạp .env và đường dẫn dự án trước)
from database import get_db
from fastapi import Depends
from geoalchemy2.shape import to_shape
from sqlalchemy import text
from sqlalchemy.orm import Session
import models
from fastapi import APIRouter
from services.openmeteo import lay_gio_hien_tai
from tinh_aqi import tinh_aqi_tong_hop, phan_loai_aqi, thang_do_cong_khai

router = APIRouter()


@router.get("/api/v1/aqi/thang-do")
def get_thang_do():
    """Thang VN_AQI (QĐ 1459/QĐ-TCMT): 6 mức, màu chuẩn, khuyến nghị sức khỏe, bảng ngưỡng nồng độ."""
    return thang_do_cong_khai()


@router.get("/api/v1/tram/{tram_id}/aqi")
def get_aqi(tram_id: int, db: Session = Depends(get_db)):
    """Tính AQI tổng hợp mới nhất cho 1 trạm."""
    result = db.execute(text("""
        SELECT ngay_do,
               COALESCE(pm25_smoothed, pm25_mean) AS pm25_mean,
               COALESCE(pm10_smoothed, pm10_mean) AS pm10_mean
        FROM du_lieu_tram_mat_dat
        WHERE tram_id = :tram_id
        ORDER BY ngay_do DESC LIMIT 1
    """), {"tram_id": tram_id}).fetchone()

    if not result:
        return {"error": "Chưa có dữ liệu"}

    aqi, chat_gay_o_nhiem = tinh_aqi_tong_hop(pm25=result.pm25_mean, pm10=result.pm10_mean)

    return {
        "ngay_do": str(result.ngay_do),
        "aqi": aqi,
        "chat_gay_o_nhiem": chat_gay_o_nhiem,
        "muc_do": phan_loai_aqi(aqi)
    }


@router.get("/api/v1/aqi-tat-ca-tram")
def get_aqi_all_stations(theo_gio: bool = False, db: Session = Depends(get_db)):
    stations = db.query(models.TramQuanTrac).filter(models.TramQuanTrac.trang_thai == "Hoat Dong").all()
    result = []

    gio_map = {}
    if theo_gio:
        co_toa_do = [t for t in stations if t.toado]
        gio = lay_gio_hien_tai([(to_shape(t.toado).y, to_shape(t.toado).x) for t in co_toa_do])
        if gio:
            gio_map = {t.id: g for t, g in zip(co_toa_do, gio)}

    for tram in stations:
        latest_md = db.execute(text("""
            SELECT ngay_do,
                   COALESCE(pm25_smoothed, pm25_mean) AS pm25_mean,
                   COALESCE(pm10_smoothed, pm10_mean) AS pm10_mean,
                   COALESCE(o3_smoothed, o3_mean) AS o3_mean
            FROM du_lieu_tram_mat_dat WHERE tram_id = :tram_id
            ORDER BY ngay_do DESC LIMIT 1
        """), {"tram_id": tram.id}).fetchone()

        latest_gee = db.execute(text("""
            SELECT no2_mean, co_mean, so2_mean
            FROM du_lieu_gee_tphcm WHERE tram_id = :tram_id
            ORDER BY ngay_do DESC LIMIT 1
        """), {"tram_id": tram.id}).fetchone()

        if latest_md:
            point = to_shape(tram.toado) if tram.toado else None
            g = gio_map.get(tram.id)
            pm25_v, pm10_v, o3_v = latest_md.pm25_mean, latest_md.pm10_mean, latest_md.o3_mean
            if g and g.get("pm25") is not None:
                pm25_v = g["pm25"]
                pm10_v = g["pm10"] if g.get("pm10") is not None else pm10_v
                o3_v = g["o3"] if g.get("o3") is not None else o3_v
            aqi, chat = tinh_aqi_tong_hop(
                pm25=pm25_v, pm10=pm10_v, o3=o3_v,
                co=latest_gee.co_mean if latest_gee else None,
                no2=latest_gee.no2_mean if latest_gee else None,
                so2=latest_gee.so2_mean if latest_gee else None
            )
            result.append({
                "tram_id": tram.id, "ma_tram": tram.ma_tram, "ten_tram": tram.ten_tram,
                "lat": point.y if point else None, "lon": point.x if point else None,
                "ngay_do": g["gio"] if g and g.get("gio") else str(latest_md.ngay_do), "pm25": pm25_v,
                "theo_gio": bool(g and g.get("pm25") is not None),
                "aqi": aqi, "chat_gay_o_nhiem": chat, "muc_do": phan_loai_aqi(aqi)
            })

    # Trạm mới (admin vừa thêm) chưa có dữ liệu trong DB: lấy tạm số liệu mô hình Open-Meteo tại đúng tọa độ trạm
    da_co = {r["tram_id"] for r in result}
    thieu = [t for t in stations if t.id not in da_co and t.toado]
    if thieu:
        gio_thieu = lay_gio_hien_tai([(to_shape(t.toado).y, to_shape(t.toado).x) for t in thieu])
        if gio_thieu:
            for t, g in zip(thieu, gio_thieu):
                if g.get("pm25") is None:
                    continue
                pt = to_shape(t.toado)
                aqi, chat = tinh_aqi_tong_hop(pm25=g["pm25"], pm10=g.get("pm10"), o3=g.get("o3"))
                result.append({
                    "tram_id": t.id, "ma_tram": t.ma_tram, "ten_tram": t.ten_tram,
                    "lat": pt.y, "lon": pt.x, "ngay_do": g["gio"], "pm25": g["pm25"],
                    "theo_gio": True, "chua_co_du_lieu_db": True,
                    "aqi": aqi, "chat_gay_o_nhiem": chat, "muc_do": phan_loai_aqi(aqi)
                })

    result.sort(key=lambda x: x['aqi'] if x['aqi'] is not None else -1, reverse=True)
    return result


@router.get("/api/v1/aqi-theo-ngay")
def get_aqi_by_day(so_ngay: int = 7, db: Session = Depends(get_db)):
    """AQI trung bình toàn khu vực theo từng ngày gần đây."""
    result = db.execute(text("""
        SELECT ngay_do, AVG(COALESCE(pm25_smoothed, pm25_mean)) as pm25_tb, AVG(COALESCE(pm10_smoothed, pm10_mean)) as pm10_tb, AVG(COALESCE(o3_smoothed, o3_mean)) as o3_tb
        FROM du_lieu_tram_mat_dat
        WHERE ngay_do IS NOT NULL
        GROUP BY ngay_do
        ORDER BY ngay_do DESC
        LIMIT :n
    """), {"n": so_ngay}).fetchall()

    data = []
    for r in reversed(result):
        aqi, chat = tinh_aqi_tong_hop(pm25=r.pm25_tb, pm10=r.pm10_tb, o3=r.o3_tb)
        data.append({
            "ngay": str(r.ngay_do),
            "aqi": aqi,
            "muc_do": phan_loai_aqi(aqi)
        })
    return data
