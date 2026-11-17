"""Lấy số liệu theo giờ từ Open-Meteo (mô hình CAMS), có bộ nhớ đệm 30 phút."""

from core import config  # noqa: F401  (nạp .env và đường dẫn dự án trước)


_cache_gio = {"t": 0.0, "key": None, "val": None}


def lay_gio_hien_tai(toa_do):
    """toa_do: list[(lat, lon)]. Trả về list dict {pm25, pm10, o3, gio} theo cùng thứ tự,
    hoặc None nếu không gọi được. PM = TB 24 giờ gần nhất, O3 = TB 8 giờ gần nhất (đến giờ hiện tại).
    Đây là giá trị MÔ HÌNH Open-Meteo (CAMS toàn cầu, lưới thô ~0,4° ≈ 45 km), không phải đo đạc."""
    import time
    import requests
    from datetime import datetime
    import pytz

    if not toa_do:
        return None
    key = tuple((round(a, 4), round(b, 4)) for a, b in toa_do)
    if _cache_gio["key"] == key and time.time() - _cache_gio["t"] < 1800:
        return _cache_gio["val"]
    try:
        resp = requests.get(
            "https://air-quality-api.open-meteo.com/v1/air-quality",
            params={
                "latitude": ",".join(str(a) for a, _ in toa_do),
                "longitude": ",".join(str(b) for _, b in toa_do),
                "hourly": "pm2_5,pm10,ozone",
                "past_hours": 24, "forecast_hours": 1,
                "timezone": "Asia/Bangkok",
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            data = [data]
        now = datetime.now(pytz.timezone("Asia/Bangkok")).replace(tzinfo=None, minute=0, second=0, microsecond=0)

        def tb(vals):
            v = [x for x in vals if x is not None]
            return round(sum(v) / len(v), 2) if v else None

        out = []
        for d in data:
            h = d["hourly"]
            idx = [i for i, t in enumerate(h["time"]) if datetime.fromisoformat(t) <= now]
            if not idx:
                out.append({"pm25": None, "pm10": None, "o3": None, "gio": None})
                continue
            last24, last8 = idx[-24:], idx[-8:]
            out.append({
                "pm25": tb([h["pm2_5"][i] for i in last24]),
                "pm10": tb([h["pm10"][i] for i in last24]),
                "o3": tb([h["ozone"][i] for i in last8]),
                "gio": h["time"][idx[-1]],
            })
        _cache_gio.update(t=time.time(), key=key, val=out)
        return out
    except Exception as exc:
        print(f"[THEO GIO] Không lấy được dữ liệu Open-Meteo: {exc}")
        return None
