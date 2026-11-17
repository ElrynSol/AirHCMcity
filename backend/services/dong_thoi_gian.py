"""Dữ liệu cho thanh thời gian trên bản đồ (theo ngày từ CSDL, theo giờ từ Open-Meteo).

Theo giờ: Open-Meteo trả chuỗi giờ của mô hình CAMS. Với khu vực ngoài châu Âu (như TP.HCM) đó là CAMS toàn cầu,
dữ liệu gốc 3 giờ/lần ở độ phân giải ~0,4° (≈45 km) rồi nội suy ra từng giờ (theo tài liệu Open-Meteo), nên các
trạm gần nhau thường nhận cùng giá trị. PM2.5/PM10 = trung bình trượt 24 giờ, O3 = 8 giờ (cùng cách tính với chế độ
"theo giờ" của bản đồ); NO2/SO2/CO theo giờ là nồng độ bề mặt của MÔ HÌNH (µg/m³), KHÁC với cột khí vệ tinh theo ngày.
"""

from core import config  # noqa: F401
import time
from datetime import datetime

BIEN_GIO = "pm2_5,pm10,ozone,nitrogen_dioxide,sulphur_dioxide,carbon_monoxide"
CHI_SO = ("aqi", "pm25", "pm10", "o3", "no2", "so2", "co")
_cache = {}
_TTL = 1800


def _tb(v):
    v = [x for x in v if x is not None]
    return sum(v) / len(v) if v else None


def _lam_tron(v, n=1):
    return None if v is None else round(v, n)


def tinh_khung_gio(du_lieu_tram, now_local, aqi_fn):
    """du_lieu_tram: list (theo trạm) dict hourly của Open-Meteo, đã gồm 24 giờ đệm ở đầu để tính trung bình trượt.
    Trả (thoi_diem, la_du_bao, theo_tram) với theo_tram[i][chi_so] = list giá trị theo từng khung."""
    ket = []
    thoi_diem, la_du_bao = None, None
    for h in du_lieu_tram:
        t = h["time"]
        n = len(t)
        if thoi_diem is None:
            thoi_diem = t[24:]
            la_du_bao = [datetime.fromisoformat(x) > now_local for x in thoi_diem]
        out = {k: [] for k in CHI_SO}
        for i in range(24, n):
            pm25 = _tb(h["pm2_5"][i - 23:i + 1])
            pm10 = _tb(h["pm10"][i - 23:i + 1])
            o3 = _tb(h["ozone"][i - 7:i + 1])
            aqi = None
            if pm25 is not None or pm10 is not None or o3 is not None:
                try:
                    aqi = aqi_fn(pm25=pm25, pm10=pm10, o3=o3)[0]
                except Exception:
                    aqi = None
            out["aqi"].append(aqi)
            out["pm25"].append(_lam_tron(pm25))
            out["pm10"].append(_lam_tron(pm10))
            out["o3"].append(_lam_tron(o3))
            out["no2"].append(_lam_tron(h["nitrogen_dioxide"][i]))
            out["so2"].append(_lam_tron(h["sulphur_dioxide"][i]))
            out["co"].append(_lam_tron(h["carbon_monoxide"][i], 0))
        ket.append(out)
    return thoi_diem or [], la_du_bao or [], ket


def lay_chuoi_gio(toa_do, gio_qua, gio_toi, get=None):
    """Gọi Open-Meteo 1 lần cho tất cả trạm. Có bộ nhớ đệm 30 phút."""
    import requests
    get = get or requests.get
    khoa = (tuple((round(a, 4), round(b, 4)) for a, b in toa_do), gio_qua, gio_toi)
    c = _cache.get(khoa)
    if c and time.time() - c[0] < _TTL:
        return c[1]
    r = get("https://air-quality-api.open-meteo.com/v1/air-quality", params={
        "latitude": ",".join(str(a) for a, _ in toa_do), "longitude": ",".join(str(b) for _, b in toa_do),
        "hourly": BIEN_GIO, "past_hours": gio_qua + 24, "forecast_hours": gio_toi, "timezone": "Asia/Bangkok"}, timeout=40)
    r.raise_for_status()
    d = r.json()
    d = d if isinstance(d, list) else [d]
    ds = [x["hourly"] for x in d]
    _cache[khoa] = (time.time(), ds)
    return ds


def tinh_khung_ngay(hang, chi_so, aqi_fn):
    """hang: các dict {tram_id, ngay_do, pm25, pm10, o3, no2, so2, co} (đã COALESCE smoothed).
    Trả (cac_ngay, {tram_id: [giá trị theo ngày]}). Chỉ giữ ngày có ít nhất 1 giá trị cho chỉ số đang xem."""
    theo = {}
    for r in hang:
        v = None
        if chi_so == "aqi":
            if r.get("pm25") is not None or r.get("pm10") is not None or r.get("o3") is not None:
                try:
                    v = aqi_fn(pm25=r.get("pm25"), pm10=r.get("pm10"), o3=r.get("o3"))[0]
                except Exception:
                    v = None
        else:
            v = r.get(chi_so)
        theo.setdefault(str(r["ngay_do"]), {})[r["tram_id"]] = v
    cac_ngay = sorted(d for d, m in theo.items() if any(x is not None for x in m.values()))
    tram_ids = {tid for m in theo.values() for tid in m}
    kq = {tid: [theo[d].get(tid) for d in cac_ngay] for tid in tram_ids}
    return cac_ngay, kq


def hang_bo_sung_ngay(du_lieu_tram, tram_ids, ngay_cuoi_db, now_local):
    """Bù các ngày SAU ngày cuối cùng trong CSDL (đến hôm nay) bằng trung bình ngày của chuỗi giờ Open-Meteo.
    Giá trị này là THÔ (chưa hiệu chỉnh không gian như dữ liệu trong CSDL); hôm nay chỉ tính đến giờ hiện tại.
    Trả list dict cùng dạng hàng CSDL: {tram_id, ngay_do, pm25, pm10, o3}."""
    from datetime import date
    hang = []
    for tid, h in zip(tram_ids, du_lieu_tram):
        gom = {}
        for i, t in enumerate(h["time"]):
            dt = datetime.fromisoformat(t)
            if dt > now_local or dt.date() <= ngay_cuoi_db:
                continue
            g = gom.setdefault(dt.date(), {"pm25": [], "pm10": [], "o3": []})
            g["pm25"].append(h["pm2_5"][i]); g["pm10"].append(h["pm10"][i]); g["o3"].append(h["ozone"][i])
        for d, g in gom.items():
            hang.append({"tram_id": tid, "ngay_do": d, "pm25": _tb(g["pm25"]), "pm10": _tb(g["pm10"]), "o3": _tb(g["o3"])})
    return hang
