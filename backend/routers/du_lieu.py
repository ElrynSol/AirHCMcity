"""Dữ liệu quan trắc: heatmap, theo giờ, đầy đủ theo trạm, nhóm ô nhiễm."""

from core import config  # noqa: F401  (nạp .env và đường dẫn dự án trước)
from database import get_db
from fastapi import Depends
from geoalchemy2.shape import to_shape
from sqlalchemy import text
from sqlalchemy.orm import Session
import models
from fastapi import APIRouter
from services.openmeteo import lay_gio_hien_tai

router = APIRouter()


@router.get("/api/v1/du-lieu-pm25")
def get_pm25_history(so_ngay: int = 30, db: Session = Depends(get_db)):
    result = db.execute(text("""
        SELECT ngay_do, pm25_mean, pm10_mean
        FROM du_lieu_tram_mat_dat
        ORDER BY ngay_do DESC LIMIT :so_ngay
    """), {"so_ngay": so_ngay}).fetchall()
    return [{"ngay_do": str(r.ngay_do), "pm25": r.pm25_mean, "pm10": r.pm10_mean} for r in reversed(result)]


@router.get("/api/v1/heatmap")
def get_heatmap_data(chi_so: str = "pm25", theo_gio: bool = False, db: Session = Depends(get_db)):
    """Lấy giá trị mới nhất của từng trạm theo chỉ số được chọn, dùng cho heatmap."""
    cac_chi_so_mat_dat = ["pm25", "pm10", "o3"]
    cac_chi_so_ve_tinh = ["no2", "co", "so2"]

    data = []
    if chi_so in cac_chi_so_mat_dat:
        # Ưu tiên giá trị đã hiệu chỉnh không gian (smoothed), không có thì dùng giá trị thô
        cot = f"COALESCE({chi_so}_smoothed, {chi_so}_mean)"
        result = db.execute(text(f"""
            SELECT DISTINCT ON (tram_id) tram_id, ngay_do, {cot} as gia_tri
            FROM du_lieu_tram_mat_dat WHERE tram_id IS NOT NULL
            ORDER BY tram_id, ngay_do DESC
        """)).fetchall()
    elif chi_so in cac_chi_so_ve_tinh:
        cot = f"{chi_so}_mean"
        result = db.execute(text(f"""
            SELECT DISTINCT ON (tram_id) tram_id, ngay_do, {cot} as gia_tri
            FROM du_lieu_gee_tphcm WHERE tram_id IS NOT NULL
            ORDER BY tram_id, ngay_do DESC
        """)).fetchall()
    else:
        return {"error": "Chỉ số không hợp lệ"}

    for r in result:
        tram = db.query(models.TramQuanTrac).filter(models.TramQuanTrac.id == r.tram_id).first()
        if tram and tram.toado and r.gia_tri is not None:
            point = to_shape(tram.toado)
            data.append({"lat": point.y, "lon": point.x, "gia_tri": r.gia_tri, "ngay_do": str(r.ngay_do)})

    # Trạm mới chưa có dữ liệu trong DB: dùng tạm số liệu mô hình Open-Meteo tại tọa độ trạm
    if chi_so in cac_chi_so_mat_dat:
        da_co = {(round(d["lat"], 5), round(d["lon"], 5)) for d in data}
        moi = []
        for t in db.query(models.TramQuanTrac).filter(models.TramQuanTrac.trang_thai == "Hoat Dong").all():
            if t.toado:
                pt = to_shape(t.toado)
                if (round(pt.y, 5), round(pt.x, 5)) not in da_co:
                    moi.append((pt.y, pt.x))
        if moi:
            gio_moi = lay_gio_hien_tai(moi)
            if gio_moi:
                for (la, lo), g in zip(moi, gio_moi):
                    if g.get(chi_so) is not None:
                        data.append({"lat": la, "lon": lo, "gia_tri": g[chi_so], "ngay_do": g["gio"], "theo_gio": True, "chua_co_du_lieu_db": True})

    # Chế độ theo giờ: chỉ áp dụng cho PM2.5/PM10/O3 (NO2/CO/SO2 vệ tinh vốn không có dữ liệu theo giờ)
    if theo_gio and chi_so in cac_chi_so_mat_dat and data:
        gio = lay_gio_hien_tai([(d["lat"], d["lon"]) for d in data])
        if gio:
            for d, g in zip(data, gio):
                if g.get(chi_so) is not None:
                    d["gia_tri"] = g[chi_so]
                    d["ngay_do"] = g["gio"]
            for d in data:
                d["theo_gio"] = True
    return data


@router.get("/api/v1/heatmap-pm25")
def get_heatmap_pm25(db: Session = Depends(get_db)):
    """Lấy giá trị PM2.5 mới nhất của từng trạm kèm tọa độ, dùng cho heatmap."""
    result = db.execute(text("""
        SELECT DISTINCT ON (tram_id) tram_id, ngay_do, pm25_mean
        FROM du_lieu_tram_mat_dat
        WHERE tram_id IS NOT NULL
        ORDER BY tram_id, ngay_do DESC
    """)).fetchall()

    data = []
    for r in result:
        tram = db.query(models.TramQuanTrac).filter(models.TramQuanTrac.id == r.tram_id).first()
        if tram and tram.toado:
            point = to_shape(tram.toado)
            data.append({"lat": point.y, "lon": point.x, "pm25": r.pm25_mean})

    return data


@router.get("/api/v1/pm25-theo-gio")
def get_pm25_hourly():
    """Lấy PM2.5 theo giờ, từ giờ hiện tại đến hết ngày mai (24h tới)."""
    import requests
    from datetime import date, timedelta, datetime
    import pytz

    tz = pytz.timezone("Asia/Bangkok")
    now = datetime.now(tz)
    today = now.date()
    tomorrow = today + timedelta(days=1)

    url = "https://air-quality-api.open-meteo.com/v1/air-quality"
    params = {
        "latitude": 10.7769, "longitude": 106.7009,
        "hourly": "pm2_5",
        "start_date": today.isoformat(), "end_date": tomorrow.isoformat(),
        "timezone": "Asia/Bangkok"
    }
    resp = requests.get(url, params=params, timeout=30)
    data = resp.json()['hourly']

    result = []
    for t, v in zip(data['time'], data['pm2_5']):
        gio_dt = datetime.fromisoformat(t)
        gio_dt = tz.localize(gio_dt) if gio_dt.tzinfo is None else gio_dt
        if gio_dt >= now.replace(minute=0, second=0, microsecond=0):
            nhan = "Bây giờ" if gio_dt.hour == now.hour and gio_dt.date() == today else f"{gio_dt.hour:02d}:00"
            result.append({"gio": nhan, "pm25": round(v, 1) if v else None})

    return result[:24]  # giới hạn 24 giờ tới


@router.get("/api/v1/tram/{tram_id}/day-du-lieu")
def get_full_data(tram_id: int, so_ngay: int = 30, db: Session = Depends(get_db)):
    gee_data = db.execute(text("""
        SELECT ngay_do, no2_mean, co_mean, so2_mean
        FROM du_lieu_gee_tphcm WHERE tram_id = :tram_id
        ORDER BY ngay_do DESC LIMIT :n
    """), {"tram_id": tram_id, "n": so_ngay}).fetchall()

    tram_data = db.execute(text("""
    SELECT ngay_do,
           COALESCE(pm25_smoothed, pm25_mean) as pm25_mean,
           COALESCE(pm10_smoothed, pm10_mean) as pm10_mean,
           COALESCE(o3_smoothed, o3_mean) as o3_mean,
           nhiet_do_mean, do_am_mean, gio_toc_do_mean
    FROM du_lieu_tram_mat_dat WHERE tram_id = :tram_id
    ORDER BY ngay_do DESC LIMIT :n
"""), {"tram_id": tram_id, "n": so_ngay}).fetchall()

    latest_gee = gee_data[0] if gee_data else None
    latest_tram = tram_data[0] if tram_data else None

    return {
        "moi_nhat": {
            "no2": latest_gee.no2_mean if latest_gee else None,
            "co": latest_gee.co_mean if latest_gee else None,
            "so2": latest_gee.so2_mean if latest_gee else None,
            "pm25": latest_tram.pm25_mean if latest_tram else None,
            "pm10": latest_tram.pm10_mean if latest_tram else None,
            "o3": latest_tram.o3_mean if latest_tram else None,
            "nhiet_do": latest_tram.nhiet_do_mean if latest_tram else None,
            "do_am": latest_tram.do_am_mean if latest_tram else None,
        },
        "lich_su": {
            "pm25": [{"ngay": str(r.ngay_do), "gia_tri": r.pm25_mean} for r in reversed(tram_data)],
            "pm10": [{"ngay": str(r.ngay_do), "gia_tri": r.pm10_mean} for r in reversed(tram_data)],
            "o3": [{"ngay": str(r.ngay_do), "gia_tri": r.o3_mean} for r in reversed(tram_data)],
            "nhiet_do": [{"ngay": str(r.ngay_do), "gia_tri": r.nhiet_do_mean} for r in reversed(tram_data)],
            "do_am": [{"ngay": str(r.ngay_do), "gia_tri": r.do_am_mean} for r in reversed(tram_data)],
            "no2": [{"ngay": str(r.ngay_do), "gia_tri": r.no2_mean} for r in reversed(gee_data)],
            "co": [{"ngay": str(r.ngay_do), "gia_tri": r.co_mean} for r in reversed(gee_data)],
            "so2": [{"ngay": str(r.ngay_do), "gia_tri": r.so2_mean} for r in reversed(gee_data)],
        }
    }


@router.get("/api/v1/du-lieu-theo-gio")
def get_hourly_data(chi_so: str = "pm2_5", ngay: str = None, lat: float = 10.7769, lon: float = 106.7009):
    import requests
    from datetime import date

    target_date = ngay if ngay else date.today().isoformat()
    ten_field = {
        "pm2_5": "pm2_5", "pm10": "pm10", "co": "carbon_monoxide",
        "no2": "nitrogen_dioxide", "so2": "sulphur_dioxide", "o3": "ozone"
    }
    field = ten_field.get(chi_so, "pm2_5")

    url = "https://air-quality-api.open-meteo.com/v1/air-quality"
    params = {
        "latitude": lat, "longitude": lon, "hourly": field,
        "start_date": target_date, "end_date": target_date,
        "timezone": "Asia/Bangkok"
    }
    resp = requests.get(url, params=params, timeout=30)
    data = resp.json()['hourly']

    result = [{"gio": t[11:16], "gia_tri": round(v, 2) if v is not None else None}
              for t, v in zip(data['time'], data[field])]
    return {"ngay": target_date, "du_lieu": result}


@router.get("/api/v1/nhom-o-nhiem")
def get_nhom_o_nhiem(db: Session = Depends(get_db)):
    result = db.execute(text("""
        SELECT id, ma_tram, ten_tram, nhom_o_nhiem, ST_Y(toado) as lat, ST_X(toado) as lon
        FROM tram_quan_trac WHERE nhom_o_nhiem IS NOT NULL
    """)).fetchall()
    return [{"id": r.id, "ma_tram": r.ma_tram, "ten_tram": r.ten_tram,
             "nhom": r.nhom_o_nhiem, "lat": r.lat, "lon": r.lon} for r in result]
