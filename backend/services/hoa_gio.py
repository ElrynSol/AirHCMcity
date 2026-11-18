"""Hoa gió và hoa gió ô nhiễm (pollution rose) theo giờ — truy vết nguồn ở mức bằng chứng B (gió và không gian).

Quy ước khí tượng (WMO):
- U > 0: không khí chuyển động về hướng Đông; V > 0: về hướng Bắc.
- WS = sqrt(U² + V²) (m/s); WD = (degrees(atan2(−U, −V)) + 360) mod 360 là hướng gió THỔI TỪ ĐÂU (Bắc = 0°, Đông = 90°).
  Ví dụ U = −2, V = −1 → WS = 2,236 m/s; WD = 63,4° (gió đến từ Đông Bắc).
Với mỗi hướng k (8 hoặc 16 hướng), trên các giờ KHÔNG lặng gió:
- F_k = n_k / N × 100%                         tần suất gió (N gồm cả giờ lặng gió, giờ lặng gió báo riêng)
- C̄_k = Σ C_t (WD_t ∈ k) / n_k                  nồng độ trung bình khi gió từ hướng k
- P_k = #{C_t > T, WD_t ∈ k} / n_k               xác suất vượt ngưỡng CÓ ĐIỀU KIỆN theo hướng (khác F_k)
- CBPF_k,s = #{C_t > P75, WD_t ∈ k, WS_t ∈ s} / n_k,s   (hàm xác suất hai biến có điều kiện theo hướng × tốc độ)
Giờ lặng gió (WS < 0,5 m/s) là một lớp riêng; hướng có ít bản ghi (< 10 giờ) bị đánh dấu "ít số liệu" để tránh kết luận sai.

Nguồn số liệu: gió 10 m theo giờ từ ERA5 (tái phân tích ECMWF, qua Open-Meteo Archive) cho quá khứ, nối với phân tích/dự báo
gần nhất của Open-Meteo cho các ngày ERA5 chưa có; PM2.5 theo giờ từ CAMS (Open-Meteo Air Quality). Thời gian giờ Việt Nam (UTC+7).
GIỚI HẠN: hoa gió ô nhiễm mô tả quan hệ THỐNG KÊ giữa hướng gió và nồng độ; nó chỉ ra hướng/khu vực nghi vấn, KHÔNG xác nhận một
cơ sở phát thải cụ thể. Gió mô hình (ô lưới ~10–30 km) không đại diện luồng gió cục bộ trong phố.
"""

from __future__ import annotations

import math
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd

TAM_TP = (10.7769, 106.7009)
LANG_GIO = 0.5                                     # m/s
LOP_TOC_DO = [(0.5, 2.0, "0,5–2 m/s"), (2.0, 4.0, "2–4 m/s"), (4.0, 99.0, "> 4 m/s")]
TEN_8 = ["Bắc", "Đông Bắc", "Đông", "Đông Nam", "Nam", "Tây Nam", "Tây", "Tây Bắc"]
VIET_TAT_8 = ["B", "ĐB", "Đ", "ĐN", "N", "TN", "T", "TB"]
TEN_16 = ["Bắc", "Bắc Đông Bắc", "Đông Bắc", "Đông Đông Bắc", "Đông", "Đông Đông Nam", "Đông Nam", "Nam Đông Nam",
          "Nam", "Nam Tây Nam", "Tây Nam", "Tây Tây Nam", "Tây", "Tây Tây Bắc", "Tây Bắc", "Bắc Tây Bắc"]
IT_SO_LIEU = 10
_cache: dict = {}
_TTL = 3600


def ws_wd(u, v):
    """Tốc độ (m/s) và hướng gió THỔI TỪ (độ, Bắc = 0) từ thành phần U (Đông) và V (Bắc)."""
    u, v = np.asarray(u, float), np.asarray(v, float)
    return np.sqrt(u ** 2 + v ** 2), (np.degrees(np.arctan2(-u, -v)) + 360) % 360


def chi_so_huong(wd, so_huong=8):
    """Hướng (độ) → chỉ số khu vực 0..so_huong-1, khu vực 0 là Bắc, tâm khu vực tại bội số 360/so_huong."""
    rong = 360 / so_huong
    return (np.floor((np.asarray(wd, float) + rong / 2) / rong) % so_huong).astype(int)


def tinh_hoa_gio(df: pd.DataFrame, nguong: float, so_huong: int = 8) -> dict:
    """df: cột ws (m/s), wd (độ, gió thổi từ), pm25 (µg/m³). Hàm thuần, dễ kiểm thử."""
    d = df.dropna(subset=["ws", "wd"]).copy()
    N = len(d)
    if N == 0:
        raise ValueError("Không có số liệu gió")
    lang = d["ws"] < LANG_GIO
    co_pm = d["pm25"].notna()
    p75 = float(d.loc[co_pm, "pm25"].quantile(0.75)) if co_pm.any() else None
    gio = d[~lang].copy()
    gio["k"] = chi_so_huong(gio["wd"], so_huong)
    ten = TEN_8 if so_huong == 8 else TEN_16
    huong = []
    for k in range(so_huong):
        g = gio[gio["k"] == k]
        n_k = len(g)
        pm = g.loc[g["pm25"].notna(), "pm25"]
        lop = []
        for lo, hi, nhan in LOP_TOC_DO:
            gs = g[(g["ws"] >= lo) & (g["ws"] < hi)]
            pms = gs.loc[gs["pm25"].notna(), "pm25"]
            lop.append({"lop": nhan, "so_gio": int(len(gs)), "tan_suat": round(len(gs) / N * 100, 2),
                        "cbpf": round(float((pms > p75).mean()), 3) if len(pms) >= 3 and p75 is not None else None})
        huong.append({
            "k": k, "ten": ten[k], "viet_tat": VIET_TAT_8[k] if so_huong == 8 else ten[k], "goc": k * 360 / so_huong,
            "so_gio": int(n_k), "tan_suat": round(n_k / N * 100, 2),                                  # F_k
            "pm25_tb": round(float(pm.mean()), 2) if len(pm) else None,                              # C̄_k
            "xac_suat_vuot": round(float((pm > nguong).mean()), 3) if len(pm) else None,             # P_k
            "so_gio_vuot": int((pm > nguong).sum()), "toc_do_tb": round(float(g["ws"].mean()), 2) if n_k else None,
            "it_so_lieu": n_k < IT_SO_LIEU, "theo_toc_do": lop})
    pm_lang = d.loc[lang & co_pm, "pm25"]
    pm_all = d.loc[co_pm, "pm25"]
    return {
        "so_gio": N, "so_huong": so_huong, "nguong": nguong, "p75_pm25": round(p75, 2) if p75 is not None else None,
        "lang_gio": {"nguong_m_s": LANG_GIO, "so_gio": int(lang.sum()), "tan_suat": round(float(lang.mean()) * 100, 2),
                     "pm25_tb": round(float(pm_lang.mean()), 2) if len(pm_lang) else None,
                     "xac_suat_vuot": round(float((pm_lang > nguong).mean()), 3) if len(pm_lang) else None},
        "tong_the": {"pm25_tb": round(float(pm_all.mean()), 2) if len(pm_all) else None,
                     "xac_suat_vuot": round(float((pm_all > nguong).mean()), 3) if len(pm_all) else None,
                     "toc_do_tb": round(float(d["ws"].mean()), 2)},
        "huong": huong,
    }


def _tai(so_ngay: int, lat: float, lon: float, get=None) -> tuple[pd.DataFrame, dict]:
    """Gió ERA5 (Archive) + phân tích gần nhất (Forecast past_days) và PM2.5 CAMS theo giờ, giờ Việt Nam."""
    import requests
    get = get or requests.get
    den = date.today() - timedelta(days=1)
    tu = den - timedelta(days=so_ngay - 1)
    phan = []
    nguon_gio = []
    # ERA5 có độ trễ ~5 ngày: lấy phần quá khứ từ Archive, phần còn lại từ Forecast (past_days ≤ 92)
    era5_den = min(den, date.today() - timedelta(days=6))
    if tu <= era5_den:
        r = get("https://archive-api.open-meteo.com/v1/archive", timeout=60, params={
            "latitude": lat, "longitude": lon, "start_date": tu.isoformat(), "end_date": era5_den.isoformat(),
            "hourly": "wind_speed_10m,wind_direction_10m", "wind_speed_unit": "ms", "timezone": "Asia/Bangkok", "models": "era5"})
        r.raise_for_status()
        h = r.json()["hourly"]
        phan.append(pd.DataFrame({"thoi_gian": h["time"], "ws": h["wind_speed_10m"], "wd": h["wind_direction_10m"]}))
        nguon_gio.append(f"ERA5 ({tu:%d/%m/%Y}–{era5_den:%d/%m/%Y})")
    con = (den - max(tu, era5_den + timedelta(days=1))).days + 1
    if con > 0:
        r = get("https://api.open-meteo.com/v1/forecast", timeout=60, params={
            "latitude": lat, "longitude": lon, "past_days": min(92, con + 1), "forecast_days": 1,
            "hourly": "wind_speed_10m,wind_direction_10m", "wind_speed_unit": "ms", "timezone": "Asia/Bangkok"})
        r.raise_for_status()
        h = r.json()["hourly"]
        f = pd.DataFrame({"thoi_gian": h["time"], "ws": h["wind_speed_10m"], "wd": h["wind_direction_10m"]})
        f = f[(f["thoi_gian"] > f"{era5_den}T23") & (f["thoi_gian"] <= f"{den}T23:59")]
        phan.append(f)
        nguon_gio.append(f"phân tích Open-Meteo ({max(tu, era5_den + timedelta(days=1)):%d/%m}–{den:%d/%m/%Y})")
    gio = pd.concat(phan, ignore_index=True).drop_duplicates("thoi_gian")
    r = get("https://air-quality-api.open-meteo.com/v1/air-quality", timeout=60, params={
        "latitude": lat, "longitude": lon, "start_date": tu.isoformat(), "end_date": den.isoformat(),
        "hourly": "pm2_5", "timezone": "Asia/Bangkok"})
    r.raise_for_status()
    h = r.json()["hourly"]
    pm = pd.DataFrame({"thoi_gian": h["time"], "pm25": h["pm2_5"]})
    df = gio.merge(pm, on="thoi_gian", how="left")
    return df, {"tu": str(tu), "den": str(den), "nguon_gio": " + ".join(nguon_gio), "nguon_pm25": "CAMS (Open-Meteo Air Quality)"}


def hoa_gio(so_ngay: int = 90, nguong: float = 25.0, so_huong: int = 8, lat: float = TAM_TP[0], lon: float = TAM_TP[1]) -> dict:
    khoa = (so_ngay, round(lat, 3), round(lon, 3))
    now = time.time()
    if khoa not in _cache or now - _cache[khoa][0] > _TTL:
        _cache[khoa] = (now, _tai(so_ngay, lat, lon))
    df, nguon = _cache[khoa][1]
    kq = tinh_hoa_gio(df, nguong, so_huong)
    kq.update({"vi_tri": {"lat": lat, "lon": lon}, **nguon, "so_ngay": so_ngay,
               "muc_bang_chung": "B — gió và không gian (pollution rose, CBPF)",
               "gioi_han": ["Hoa gió ô nhiễm mô tả quan hệ thống kê giữa hướng gió và nồng độ, chỉ ra hướng nghi vấn, "
                            "không xác nhận một cơ sở phát thải cụ thể.",
                            "Gió mô hình (ô lưới ERA5 ~30 km) không đại diện luồng gió cục bộ trong đô thị.",
                            "PM2.5 là số liệu mô hình CAMS (~45 km), chưa phải số đo trạm mặt đất.",
                            f"Hướng có dưới {IT_SO_LIEU} giờ số liệu được đánh dấu 'ít số liệu', không nên kết luận."]})
    return kq
