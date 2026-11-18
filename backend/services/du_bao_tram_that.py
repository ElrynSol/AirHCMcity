"""Dự báo PM2.5 ngày mai từ SỐ ĐO THẬT (điểm CMT8, AirGradient qua OpenAQ) — mô hình ml/mo_hinh_tram_that.py.

Đầu vào lúc vận hành: số đo thật 8 ngày gần nhất (OpenAQ, cần OPENAQ_API_KEY), dự báo CAMS và dự báo thời tiết cho ngày mai
(Open-Meteo). Trả kèm dự báo "mai = hôm nay" để người xem so sánh. Kết quả lưu đệm 1 giờ.
"""
from __future__ import annotations

import os
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd
import requests

from core.config import PROJECT_ROOT

_dem = {"t": 0.0, "v": None}
_TTL = 3600


def _openaq_gio(ma_cam_bien: int, tu: date, den: date) -> pd.DataFrame:
    khoa = os.getenv("OPENAQ_API_KEY", "").strip()
    if not khoa:
        raise RuntimeError("Chưa cấu hình OPENAQ_API_KEY")
    r = requests.get(f"https://api.openaq.org/v3/sensors/{ma_cam_bien}/hours", timeout=60, headers={"X-API-Key": khoa},
                     params={"datetime_from": f"{tu}T00:00:00Z", "datetime_to": f"{den}T23:59:59Z", "limit": 1000})
    r.raise_for_status()
    hang = [(((x.get("period") or {}).get("datetimeFrom") or {}).get("utc"), x.get("value")) for x in r.json().get("results", [])]
    d = pd.DataFrame([h for h in hang if h[0] and h[1] is not None and 0 <= h[1] < 900], columns=["utc", "pm25"])
    if d.empty:
        return pd.DataFrame(columns=["ngay", "y"])
    d["t"] = pd.to_datetime(d["utc"], utc=True).dt.tz_convert("Asia/Bangkok").dt.tz_localize(None)
    g = d.groupby(d["t"].dt.normalize())["pm25"].agg(["mean", "count"])
    g = g[g["count"] >= 18]
    return pd.DataFrame({"ngay": g.index, "y": g["mean"].values})


def _ma_cam_bien(ma_tram: int) -> int:
    khoa = os.getenv("OPENAQ_API_KEY", "").strip()
    r = requests.get(f"https://api.openaq.org/v3/locations/{ma_tram}", timeout=30, headers={"X-API-Key": khoa})
    r.raise_for_status()
    loc = r.json()["results"][0]
    return next(s["id"] for s in loc["sensors"] if (s.get("parameter") or {}).get("id") == 2)


def du_bao() -> dict:
    now = time.time()
    if _dem["v"] is not None and now - _dem["t"] < _TTL:
        return _dem["v"]
    import joblib
    goi = joblib.load(PROJECT_ROOT / "models" / "du_bao_tram_that.joblib")
    tram, hom_nay = goi["tram"], date.today()
    do = _openaq_gio(_ma_cam_bien(tram["ma"]), hom_nay - timedelta(days=9), hom_nay)
    do = do[do["ngay"] < pd.Timestamp(hom_nay)]           # chỉ ngày đã trọn (hôm nay chưa hết ngày)
    if len(do) < 5:
        raise RuntimeError("Điểm đo thật chưa đủ số liệu 7 ngày gần đây")
    cuoi = do["ngay"].max()
    if (pd.Timestamp(hom_nay) - cuoi).days > 1:
        raise RuntimeError(f"Số đo thật mới đến {cuoi:%d/%m/%Y}, quá cũ để dự báo ngày mai")
    mai = (cuoi + pd.Timedelta(days=1)).date()
    aq = requests.get("https://air-quality-api.open-meteo.com/v1/air-quality", timeout=30, params={
        "latitude": tram["lat"], "longitude": tram["lon"], "hourly": "pm2_5", "start_date": str(mai), "end_date": str(mai),
        "timezone": "Asia/Bangkok"}).json()["hourly"]
    tt = requests.get("https://api.open-meteo.com/v1/forecast", timeout=30, params={
        "latitude": tram["lat"], "longitude": tram["lon"], "start_date": str(mai), "end_date": str(mai), "timezone": "Asia/Bangkok",
        "daily": "temperature_2m_mean,relative_humidity_2m_mean,wind_speed_10m_mean,precipitation_sum"}).json()["daily"]
    y = do.set_index("ngay")["y"]
    x = {"y": float(y.iloc[-1]), "y_lag1": float(y.iloc[-2]) if len(y) >= 2 else float(y.iloc[-1]), "y_tb7": float(y.tail(7).mean()),
         "cams_mai": float(np.nanmean([v for v in aq["pm2_5"] if v is not None])),
         "nhiet_do_mai": tt["temperature_2m_mean"][0], "do_am_mai": tt["relative_humidity_2m_mean"][0],
         "gio_mai": tt["wind_speed_10m_mean"][0], "mua_mai": tt["precipitation_sum"][0],
         "thang_sin": float(np.sin(2 * np.pi * mai.month / 12)), "thang_cos": float(np.cos(2 * np.pi * mai.month / 12))}
    p = float(goi["mo_hinh"].predict(pd.DataFrame([x])[goi["dac_trung"]].values)[0])
    kq = {"tram": tram, "ngay_du_bao": str(mai), "pm25_du_bao": round(p, 1), "pm25_hom_nay_do_that": round(x["y"], 1),
          "pm25_tb7_do_that": round(x["y_tb7"], 1), "cams_du_bao_mai": round(x["cams_mai"], 1),
          "so_ngay_do_that": [{"ngay": f"{d:%Y-%m-%d}", "pm25": round(float(v), 1)} for d, v in y.items()],
          "nguon": "Số đo thật: OpenAQ (AirGradient). Dự báo CAMS và thời tiết ngày mai: Open-Meteo.",
          "luu_y": "Một điểm đo (cảm biến giá rẻ) ở quận 3 cũ, chưa đại diện cả thành phố. Trên 194 ngày kiểm tra, mô hình tốt hơn "
                   "\"mai = hôm nay\" khoảng 5% (chưa có ý nghĩa thống kê); CAMS thô kém hơn rõ rệt."}
    _dem.update(t=now, v=kq)
    return kq
