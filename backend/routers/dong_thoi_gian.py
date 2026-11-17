"""API cho thanh thời gian trên bản đồ: /api/v1/dong-thoi-gian"""

from core import config  # noqa: F401
from database import get_db
from fastapi import APIRouter, Depends, HTTPException
from geoalchemy2.shape import to_shape
from sqlalchemy import text
from sqlalchemy.orm import Session
from datetime import datetime
import models
from core import logbus
from services.aqi import _aqi_helpers
from services import dong_thoi_gian as dtg

router = APIRouter()

DON_VI_NGAY = {"aqi": "AQI", "pm25": "µg/m³", "pm10": "µg/m³", "o3": "µg/m³", "no2": "mol/m²", "so2": "mol/m²", "co": "mol/m²"}
DON_VI_GIO = {"aqi": "AQI", "pm25": "µg/m³", "pm10": "µg/m³", "o3": "µg/m³", "no2": "µg/m³", "so2": "µg/m³", "co": "µg/m³"}


def _tram_hoat_dong(db):
    ds = []
    for t in db.query(models.TramQuanTrac).filter(models.TramQuanTrac.trang_thai == "Hoat Dong").all():
        if t.toado is not None:
            p = to_shape(t.toado)
            ds.append({"id": t.id, "ma_tram": t.ma_tram, "ten_tram": t.ten_tram, "lat": p.y, "lon": p.x})
    return ds


@router.get("/api/v1/dong-thoi-gian")
def dong_thoi_gian(chi_so: str = "aqi", buoc: str = "ngay", so_buoc: int = None, gio_toi: int = 24,
                   db: Session = Depends(get_db)):
    if chi_so not in dtg.CHI_SO:
        raise HTTPException(status_code=400, detail="Chỉ số không hợp lệ")
    if buoc not in ("ngay", "gio"):
        raise HTTPException(status_code=400, detail="buoc phải là 'ngay' hoặc 'gio'")
    tinh_aqi_tong_hop, _ = _aqi_helpers()
    tram = _tram_hoat_dong(db)
    if not tram:
        raise HTTPException(status_code=404, detail="Chưa có trạm hoạt động")

    if buoc == "ngay":
        n = max(7, min(so_buoc or 30, 180))
        hang = []
        if chi_so in ("aqi", "pm25", "pm10", "o3"):
            rows = db.execute(text("""
                SELECT tram_id, ngay_do, COALESCE(pm25_smoothed, pm25_mean) AS pm25,
                       COALESCE(pm10_smoothed, pm10_mean) AS pm10, COALESCE(o3_smoothed, o3_mean) AS o3
                FROM du_lieu_tram_mat_dat
                WHERE tram_id IS NOT NULL AND ngay_do > (SELECT MAX(ngay_do) FROM du_lieu_tram_mat_dat) - CAST(:n AS INTEGER)
            """), {"n": n}).fetchall()
            hang = [dict(r._mapping) for r in rows]
            # Bù các ngày chưa có trong CSDL (đến hôm nay) bằng Open-Meteo để thanh thời gian bám theo hiện tại
            bo_sung_tu = None
            try:
                import pytz
                now = datetime.now(pytz.timezone("Asia/Bangkok")).replace(tzinfo=None, minute=0, second=0, microsecond=0)
                cuoi = max((r["ngay_do"] for r in hang), default=None)
                if cuoi is not None and cuoi < now.date():
                    thieu = (now.date() - cuoi).days
                    ds = dtg.lay_chuoi_gio([(t["lat"], t["lon"]) for t in tram], thieu * 24 + 24, 1)
                    # lay_chuoi_gio cộng thêm 24 giờ đệm ở đầu, bỏ phần đệm không ảnh hưởng vì lọc theo ngày
                    them = dtg.hang_bo_sung_ngay(ds, [t["id"] for t in tram], cuoi, now)
                    if them:
                        hang += them
                        bo_sung_tu = str(min(r["ngay_do"] for r in them))
            except Exception as exc:
                logbus.ghi("WARN", "dong_thoi_gian", "bo_sung_that_bai", f"Không bù được ngày mới từ Open-Meteo: {type(exc).__name__}")
            nguon = ("PM2.5, PM10, O₃: trung bình ngày từ mô hình Open-Meteo/CAMS, đã hiệu chỉnh không gian (ước tính, chưa kiểm chứng đo đạc). "
                     "AQI tính theo VN_AQI (QĐ 1459/QĐ-TCMT) từ các giá trị này.")
        else:
            cot = f"{chi_so}_mean"
            rows = db.execute(text(f"""
                SELECT tram_id, ngay_do, {cot} AS {chi_so}
                FROM du_lieu_gee_tphcm
                WHERE tram_id IS NOT NULL AND ngay_do > (SELECT MAX(ngay_do) FROM du_lieu_gee_tphcm) - CAST(:n AS INTEGER)
            """), {"n": n}).fetchall()
            hang = [dict(r._mapping) for r in rows]
            nguon = "NO₂, CO, SO₂: cột khí vệ tinh Sentinel-5P (mol/m², không phải nồng độ mặt đất), chỉ có vào những ngày vệ tinh quan sát được."
        if chi_so not in ("aqi", "pm25", "pm10", "o3"):
            bo_sung_tu = None
        cac_moc, theo = dtg.tinh_khung_ngay(hang, chi_so, tinh_aqi_tong_hop)
        la_bo_sung = [bool(bo_sung_tu and d >= bo_sung_tu) for d in cac_moc]
        if bo_sung_tu:
            nguon += (f" Từ {bo_sung_tu} dữ liệu CSDL chưa cập nhật: các ngày này được bù bằng trung bình ngày của mô hình Open-Meteo "
                      "(giá trị THÔ, chưa hiệu chỉnh không gian; hôm nay chỉ tính đến giờ hiện tại).")
        for t in tram:
            gt = theo.get(t["id"], [None] * len(cac_moc))
            t["gia_tri"] = [None if v is None else float(f"{v:.4g}") for v in gt]
        return {"chi_so": chi_so, "buoc": "ngay", "don_vi": DON_VI_NGAY[chi_so], "thoi_diem": cac_moc,
                "la_du_bao": [False] * len(cac_moc), "la_bo_sung": la_bo_sung, "tram": tram, "nguon": nguon}

    # theo giờ
    gio_qua = max(24, min(so_buoc or 72, 168))
    gio_toi = max(0, min(gio_toi, 48))
    try:
        ds = dtg.lay_chuoi_gio([(t["lat"], t["lon"]) for t in tram], gio_qua, gio_toi)
        import pytz
        now = datetime.now(pytz.timezone("Asia/Bangkok")).replace(tzinfo=None, minute=0, second=0, microsecond=0)
        moc, du_bao, theo = dtg.tinh_khung_gio(ds, now, tinh_aqi_tong_hop)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Không lấy được dữ liệu theo giờ từ Open-Meteo ({type(exc).__name__}). Thử lại sau.")
    for t, kq in zip(tram, theo):
        t["gia_tri"] = kq[chi_so]
    nguon = ("Mô hình CAMS qua Open-Meteo: dữ liệu gốc 3 giờ/lần, độ phân giải ~0,4° (≈45 km), nội suy theo giờ; các trạm gần nhau thường cùng giá trị. "
             "PM2.5/PM10 = trung bình trượt 24 giờ, O₃ = 8 giờ, AQI tính theo VN_AQI (QĐ 1459/QĐ-TCMT) từ các giá trị này. Các khung sau thời điểm hiện tại là DỰ BÁO của mô hình.")
    if chi_so in ("no2", "so2", "co"):
        nguon += f" {chi_so.upper()} theo giờ là nồng độ bề mặt của MÔ HÌNH (µg/m³), khác với cột khí vệ tinh trong chế độ theo ngày."
    return {"chi_so": chi_so, "buoc": "gio", "don_vi": DON_VI_GIO[chi_so], "thoi_diem": moc, "la_du_bao": du_bao, "tram": tram, "nguon": nguon}
