"""API dự báo PM2.5 theo giờ (24 giờ tới): GET /api/v1/du-bao-gio và GET /api/v1/du-bao-gio/chi-so"""

from core import config  # noqa: F401
from core import logbus
from fastapi import APIRouter, HTTPException
from datetime import datetime
import pandas as pd
import time

from services import du_bao_gio as dbg
from services.aqi import _aqi_helpers

router = APIRouter()

LAT, LON = 10.7769, 106.7009          # điểm đại diện trung tâm TP.HCM (cùng điểm với các trang khác)
NGUONG_QCVN_PM25_24H = 50.0           # QCVN 05:2023/BTNMT, trung bình 24 giờ
NGUONG_WHO_PM25_24H = 15.0            # Khuyến nghị WHO 2021, trung bình 24 giờ
_cache = {"t": 0, "v": None}
_TTL = 900


def _lay_chuoi_gan_day(get=None):
    """Chuỗi giờ liên tục ~4 ngày gần nhất (PM2.5, PM10, thời tiết) + dự báo thô CAMS cho 24 giờ tới."""
    import requests
    get = get or requests.get
    aq = get("https://air-quality-api.open-meteo.com/v1/air-quality", params={
        "latitude": LAT, "longitude": LON, "hourly": "pm2_5,pm10", "past_hours": 96, "forecast_hours": 25,
        "timezone": "Asia/Bangkok"}, timeout=30)
    aq.raise_for_status()
    th = get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": LAT, "longitude": LON, "past_hours": 96, "forecast_hours": 1,
        "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation,surface_pressure",
        "timezone": "Asia/Bangkok"}, timeout=30)
    th.raise_for_status()
    a = pd.DataFrame(aq.json()["hourly"])
    t = pd.DataFrame(th.json()["hourly"])
    return a, t


@router.get("/api/v1/du-bao-gio/chi-so")
def chi_so_mo_hinh():
    cs = dbg.doc_chi_so()
    if not cs:
        raise HTTPException(status_code=404, detail="Chưa có số liệu đánh giá. Chạy: python ml/train_du_bao_gio.py")
    return cs


@router.get("/api/v1/du-bao-gio")
def du_bao_theo_gio():
    if time.time() - _cache["t"] < _TTL and _cache["v"]:
        return _cache["v"]
    obj = dbg.tai_mo_hinh()
    if obj is None:
        raise HTTPException(status_code=503, detail="Chưa huấn luyện mô hình theo giờ. Chạy: python ml/train_du_bao_gio.py")
    try:
        a, t = _lay_chuoi_gan_day()
    except Exception as exc:
        logbus.ghi("WARN", "du_bao_gio", "lay_du_lieu_that_bai", f"{type(exc).__name__}: {exc}")
        raise HTTPException(status_code=502, detail=f"Không lấy được dữ liệu gần đây từ Open-Meteo ({type(exc).__name__}). Thử lại sau.")
    import pytz
    now = datetime.now(pytz.timezone("Asia/Bangkok")).replace(tzinfo=None, minute=0, second=0, microsecond=0)
    a["time"] = pd.to_datetime(a["time"])
    t["time"] = pd.to_datetime(t["time"])
    gop = a.merge(t, on="time", how="left")
    quan_sat = gop[gop["time"] <= now].copy()
    try:
        kq = dbg.du_bao_24h(quan_sat[dbg.CAC_COT], obj)
    except Exception as exc:
        logbus.ghi("ERROR", "du_bao_gio", "du_bao_that_bai", f"{type(exc).__name__}: {exc}")
        raise HTTPException(status_code=500, detail=f"Không tạo được dự báo: {exc}")

    # CAMS thô (dự báo của chính Open-Meteo) để đối chiếu trên biểu đồ
    cams = {str(r.time)[:13] + ":00": (None if pd.isna(r.pm2_5) else round(float(r.pm2_5), 1)) for r in gop.itertuples()}
    for x in kq["du_bao"]:
        x["cams_tho"] = cams.get(x["gio"].replace("T", " "))

    # AQI: trung bình trượt 24 giờ của (quan sát + dự báo) → VN_AQI QĐ 1459 (chỉ theo PM2.5 vì đây là dự báo PM2.5)
    tinh_aqi_tong_hop, phan_loai_aqi = _aqi_helpers()
    gan = [float(v) for v in quan_sat["pm2_5"].dropna().tail(24)]
    chuoi = gan[:]
    for x in kq["du_bao"]:
        chuoi.append(x["pm25"])
        tb24 = sum(chuoi[-24:]) / len(chuoi[-24:])
        try:
            x["aqi"] = tinh_aqi_tong_hop(pm25=tb24)[0]
        except Exception:
            x["aqi"] = None
    pm_24h_toi = [x["pm25"] for x in kq["du_bao"]]
    tb = sum(pm_24h_toi) / len(pm_24h_toi)
    tot, xau = dbg.khung_gio_tot_xau(kq["du_bao"], 3)
    cs = dbg.doc_chi_so() or {}
    kq.update({
        "tb_24h_toi": round(tb, 1),
        "so_gio_tren_who": sum(1 for v in pm_24h_toi if v > NGUONG_WHO_PM25_24H),
        "so_gio_tren_qcvn": sum(1 for v in pm_24h_toi if v > NGUONG_QCVN_PM25_24H),
        "nguong": {"qcvn_24h": NGUONG_QCVN_PM25_24H, "who_24h": NGUONG_WHO_PM25_24H},
        "khung_tot": tot, "khung_xau": xau,
        "mo_hinh": {"ten": "HistGradientBoosting (trực tiếp 1–24 giờ)",
                    "ky_nang_6h": (cs.get("theo_buoc", {}).get("6") or {}).get("ky_nang_so_voi_persistence"),
                    "ky_nang_24h": (cs.get("theo_buoc", {}).get("24") or {}).get("ky_nang_so_voi_persistence"),
                    "r2_24h": (cs.get("theo_buoc", {}).get("24") or {}).get("r2"),
                    "kiem_tra_tu": cs.get("kiem_tra_tu")},
        "luu_y": ("Mô hình học máy huấn luyện trên chuỗi PM2.5 tái phân tích CAMS (lưới ~0,4°). "
                  "Khoảng thấp–cao là phân vị 10–90% của sai số thực trên tập kiểm tra. So sánh ngưỡng dùng trung bình 24 giờ."),
    })
    _cache.update({"t": time.time(), "v": kq})
    return kq
