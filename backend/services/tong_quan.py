"""Số liệu cho trang Tổng quan (một lần gọi, có bộ nhớ đệm 60 giây).

- AQI hiện tại toàn TP: PM2.5/PM10 trung bình 24 giờ trượt, O3 trung bình 8 giờ (Open-Meteo/CAMS theo giờ) của từng trạm
  → AQI từng trạm theo QĐ 1459 → AQI TP tính từ nồng độ trung bình các trạm (cùng cách với /aqi-theo-ngay).
  Không gọi được Open-Meteo thì dùng trung bình ngày mới nhất trong CSDL (ghi rõ nguồn trong kết quả).
- So với hôm qua: AQI ngày gần nhất trong CSDL.
- So với ngưỡng: PM2.5 TB 24 giờ so với WHO 2021 (15 µg/m³) và QCVN 05:2023 (50 µg/m³).
- Thời tiết hiện tại: Open-Meteo forecast (current), đệm 15 phút.
- Dự báo 24 giờ: lấy từ /du-bao-gio (đã có đệm riêng); lỗi thì bỏ qua phần này.
"""

from core import config  # noqa: F401
import time
from datetime import datetime, timedelta

import requests
from geoalchemy2.shape import to_shape
from sqlalchemy import text

import models
from database import SessionLocal
from services.openmeteo import lay_gio_hien_tai
from tinh_aqi import tinh_aqi_tong_hop, muc_aqi, THANG_AQI

NGUONG_WHO_PM25 = 15.0
NGUONG_QCVN_PM25 = 50.0
TAM_TP = (10.7769, 106.7009)
_dem = {"t": 0.0, "v": None}
_dem_tt = {"t": 0.0, "v": None}

# Mã thời tiết WMO (Open-Meteo) → mô tả + biểu tượng
_THOI_TIET = [((0,), "Trời quang", "☀️"), ((1,), "Ít mây", "🌤️"), ((2,), "Có mây", "⛅"), ((3,), "Nhiều mây", "☁️"),
              ((45, 48), "Sương mù", "🌫️"), ((51, 53, 55, 56, 57), "Mưa phùn", "🌦️"), ((61, 63, 66), "Mưa", "🌧️"),
              ((65, 67), "Mưa to", "🌧️"), ((80, 81), "Mưa rào", "🌦️"), ((82,), "Mưa rào mạnh", "⛈️"),
              ((95, 96, 99), "Dông", "⛈️")]


def _r(x, n=1):
    return None if x is None else round(float(x), n)


def _muc(aqi):
    m = muc_aqi(aqi)
    return {"aqi": aqi, "muc": m["muc"] if m else None, "mau": m["mau"] if m else None}


def thoi_tiet_hien_tai():
    if _dem_tt["v"] and time.time() - _dem_tt["t"] < 900:
        return _dem_tt["v"]
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=12, params={
            "latitude": TAM_TP[0], "longitude": TAM_TP[1], "timezone": "Asia/Bangkok",
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m,precipitation,weather_code,uv_index"})
        r.raise_for_status()
        c = r.json()["current"]
        ma = c.get("weather_code")
        mo_ta, bt = next(((m, b) for ma_s, m, b in _THOI_TIET if ma in ma_s), ("--", "🌡️"))
        v = {"nhiet_do": _r(c.get("temperature_2m")), "cam_giac": _r(c.get("apparent_temperature")),
             "do_am": _r(c.get("relative_humidity_2m"), 0), "gio_kmh": _r(c.get("wind_speed_10m")),
             "mua_mm": _r(c.get("precipitation")), "uv": _r(c.get("uv_index")), "mo_ta": mo_ta, "bieu_tuong": bt,
             "luc": (c.get("time") or "").replace("T", " ")}
        _dem_tt.update(t=time.time(), v=v)
        return v
    except Exception:
        return _dem_tt["v"]


def _tram_hien_tai(db):
    """[(tram, pm25, pm10, o3, gio, nguon)] cho trạm đang hoạt động: ưu tiên số liệu theo giờ, thiếu thì lấy ngày mới nhất trong CSDL."""
    tram = db.query(models.TramQuanTrac).filter(models.TramQuanTrac.trang_thai == "Hoat Dong").all()
    co_toa_do = [t for t in tram if t.toado]
    gio = lay_gio_hien_tai([(to_shape(t.toado).y, to_shape(t.toado).x) for t in co_toa_do]) or []
    theo_gio = {t.id: g for t, g in zip(co_toa_do, gio) if g and g.get("pm25") is not None}
    ngay = {r.tram_id: r for r in db.execute(text("""
        SELECT DISTINCT ON (tram_id) tram_id, ngay_do, COALESCE(pm25_smoothed, pm25_mean) AS pm25,
               COALESCE(pm10_smoothed, pm10_mean) AS pm10, COALESCE(o3_smoothed, o3_mean) AS o3
        FROM du_lieu_tram_mat_dat ORDER BY tram_id, ngay_do DESC""")).fetchall()}
    out = []
    for t in tram:
        g = theo_gio.get(t.id)
        if g:
            out.append((t, g["pm25"], g.get("pm10"), g.get("o3"), g.get("gio"), "gio"))
        elif t.id in ngay:
            r = ngay[t.id]
            out.append((t, r.pm25, r.pm10, r.o3, str(r.ngay_do), "ngay"))
    return out


def tong_quan():
    if _dem["v"] and time.time() - _dem["t"] < 60:
        return _dem["v"]
    db = SessionLocal()
    try:
        ds = _tram_hien_tai(db)
        xep_hang = []
        for t, pm25, pm10, o3, gio, nguon in ds:
            aqi, chat = tinh_aqi_tong_hop(pm25=pm25, pm10=pm10, o3=o3)
            p = to_shape(t.toado) if t.toado else None
            xep_hang.append({"id": t.id, "ma": t.ma_tram, "ten": t.ten_tram, "lat": p.y if p else None, "lon": p.x if p else None,
                             "pm25": _r(pm25), "chat": chat, "nguon": nguon, **_muc(aqi)})
        xep_hang = [x for x in xep_hang if x["aqi"] is not None]
        xep_hang.sort(key=lambda x: x["aqi"])

        tb = lambda i: (lambda v: sum(v) / len(v) if v else None)([x[i] for x in ds if x[i] is not None])
        pm25, pm10, o3 = tb(1), tb(2), tb(3)
        aqi_tp, chat_tp = tinh_aqi_tong_hop(pm25=pm25, pm10=pm10, o3=o3)
        theo_gio = any(x[5] == "gio" for x in ds)
        gio_sl = max((x[4] for x in ds if x[5] == "gio" and x[4]), default=None)

        phan_bo = {m["muc"]: 0 for m in THANG_AQI}
        for x in xep_hang:
            phan_bo[x["muc"]] += 1

        ngay_rows = db.execute(text("""
            SELECT ngay_do, AVG(COALESCE(pm25_smoothed, pm25_mean)) AS pm25, AVG(COALESCE(pm10_smoothed, pm10_mean)) AS pm10,
                   AVG(COALESCE(o3_smoothed, o3_mean)) AS o3
            FROM du_lieu_tram_mat_dat WHERE ngay_do >= CURRENT_DATE - 14
            GROUP BY ngay_do ORDER BY ngay_do""")).fetchall()
        xu_huong = []
        for r in ngay_rows:
            a, _ = tinh_aqi_tong_hop(pm25=r.pm25, pm10=r.pm10, o3=r.o3)
            xu_huong.append({"ngay": str(r.ngay_do), "pm25": _r(r.pm25), **_muc(a)})
        hom_qua = xu_huong[-1] if xu_huong else None
    finally:
        db.close()

    du_bao = None
    try:
        from routers.du_bao_gio import du_bao_theo_gio
        d = du_bao_theo_gio()
        du_bao = {"gio": [{"gio": x["gio"], "pm25": x["pm25"], **_muc(x.get("aqi"))} for x in d["du_bao"]],
                  "tb_24h_toi": d.get("tb_24h_toi"), "khung_tot": d.get("khung_tot"), "khung_xau": d.get("khung_xau"),
                  "so_gio_tren_who": d.get("so_gio_tren_who"),
                  "aqi_cao_nhat": max((x.get("aqi") or 0) for x in d["du_bao"]) or None}
    except Exception:
        pass

    iot = None
    try:
        from routers.iot import ds_thiet_bi
        song = [t for t in ds_thiet_bi() if t.get("truc_tuyen")]
        if song:
            iot = [{"ma": t["ma"], "ten": t["ten"], "pm25": t["pm25"], **_muc(t["aqi"])} for t in song]
    except Exception:
        pass

    m = muc_aqi(aqi_tp)
    v = {
        "cap_nhat": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "hien_tai": {**_muc(aqi_tp), "chat": chat_tp, "pm25": _r(pm25), "pm10": _r(pm10), "o3": _r(o3),
                     "so_tram": len(xep_hang), "theo_gio": theo_gio, "gio_so_lieu": gio_sl,
                     "y_nghia": m["y_nghia"] if m else None, "nguoi_binh_thuong": m["nguoi_binh_thuong"] if m else None,
                     "nhom_nhay_cam": m["nhom_nhay_cam"] if m else None},
        "nguong": {"who": NGUONG_WHO_PM25, "qcvn": NGUONG_QCVN_PM25,
                   "lan_who": _r(pm25 / NGUONG_WHO_PM25, 1) if pm25 else None,
                   "phan_tram_qcvn": round(pm25 / NGUONG_QCVN_PM25 * 100) if pm25 else None},
        "so_voi_hom_qua": ({"ngay": hom_qua["ngay"], "aqi": hom_qua["aqi"], "chenh": (aqi_tp - hom_qua["aqi"]) if aqi_tp is not None and hom_qua["aqi"] is not None else None}
                           if hom_qua else None),
        "phan_bo": phan_bo,
        "xep_hang": xep_hang,
        "xu_huong": xu_huong,
        "du_bao": du_bao,
        "thoi_tiet": thoi_tiet_hien_tai(),
        "iot": iot,
    }
    _dem.update(t=time.time(), v=v)
    return v
