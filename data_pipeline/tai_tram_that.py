"""Tải số liệu PM2.5 ĐO THẬT tại các trạm mặt đất quanh TP.HCM từ OpenAQ, lưu vào PostGIS và đối chiếu với CAMS.

OpenAQ (openaq.org) gom số liệu từ trạm quan trắc chính phủ, trạm Tổng Lãnh sự quán Mỹ (AirNow) và cảm biến.
Cần khóa API MIỄN PHÍ: đăng ký tại https://explore.openaq.org → Account → API Key, rồi thêm vào .env:
    OPENAQ_API_KEY=...

Chạy từ thư mục gốc dự án:
    python data_pipeline/tai_tram_that.py --liet-ke                 # liệt kê trạm đo PM2.5 trong 25 km quanh trung tâm
    python data_pipeline/tai_tram_that.py --tu 2025-01-01           # tải số liệu theo giờ của mọi trạm tới hôm nay
    python data_pipeline/tai_tram_that.py --tu 2025-01-01 --tram 1234,5678   # chỉ một số trạm (mã location OpenAQ)

Kết quả:
- Bảng `tram_do_that` (mã OpenAQ, tên, nhà cung cấp, toado Point PostGIS) và `do_that_gio` (giờ, PM2.5 µg/m³).
- `du_lieu/tram_that/<ma>.csv` (thoi_gian, pm25) — nạp được vào data_pipeline/doi_chieu_tram_that.py.
- `models/doi_chieu_tram_that.json`: so sánh PM2.5 đo thật với CAMS (Open-Meteo) cùng vị trí, theo ngày và theo giờ:
  sai lệch trung bình (bias), MAE, RMSE, tương quan, và hệ số hiệu chỉnh tuyến tính CAMS → đo thật.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC / "data_pipeline"))
API = "https://api.openaq.org/v3"
TAM = (10.7769, 106.7009)       # trung tâm TP.HCM
BAN_KINH_M = 25000              # OpenAQ v3 cho tối đa 25 km
MA_PM25 = 2                     # parameters_id của PM2.5 trong OpenAQ
THU_MUC = GOC / "du_lieu" / "tram_that"

DDL = [
    """CREATE TABLE IF NOT EXISTS tram_do_that (
        ma INTEGER PRIMARY KEY,                -- mã location của OpenAQ
        ten TEXT NOT NULL,
        nha_cung_cap TEXT,
        la_cam_bien_re BOOLEAN,                -- OpenAQ: isMonitor = false → cảm biến giá rẻ, kém chính xác hơn trạm chuẩn
        ma_cam_bien_pm25 INTEGER,
        toado geometry(Point, 4326),
        cap_nhat TIMESTAMPTZ NOT NULL DEFAULT NOW())""",
    "CREATE INDEX IF NOT EXISTS ix_tram_do_that_toado ON tram_do_that USING GIST (toado)",
    """CREATE TABLE IF NOT EXISTS do_that_gio (
        ma_tram INTEGER NOT NULL REFERENCES tram_do_that(ma) ON DELETE CASCADE,
        gio TIMESTAMP NOT NULL,                -- giờ Việt Nam (UTC+7), đầu giờ
        pm25 REAL NOT NULL,
        PRIMARY KEY (ma_tram, gio))""",
]


def _nap_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(GOC / ".env")
    except ImportError:
        pass


def _goi(duong, **ts):
    khoa = os.getenv("OPENAQ_API_KEY", "").strip()
    if not khoa:
        sys.exit("Thiếu OPENAQ_API_KEY trong .env — đăng ký miễn phí tại https://explore.openaq.org (Account → API Key).")
    for lan in range(5):
        r = requests.get(API + duong, params=ts, headers={"X-API-Key": khoa, "User-Agent": "AirHCM-do-an"}, timeout=60)
        if r.status_code == 429:                       # giới hạn tốc độ: chờ rồi thử lại
            time.sleep(int(r.headers.get("x-ratelimit-reset", 10)) + 1)
            continue
        if r.status_code in (401, 403):
            sys.exit("OpenAQ từ chối khóa API (sai khóa hoặc chưa kích hoạt).")
        r.raise_for_status()
        time.sleep(1.1)                                # ~60 lời gọi/phút theo giới hạn gói miễn phí
        return r.json()
    raise RuntimeError("OpenAQ từ chối do vượt giới hạn tốc độ nhiều lần")


def tim_tram() -> list[dict]:
    d = _goi("/locations", coordinates=f"{TAM[0]},{TAM[1]}", radius=BAN_KINH_M, parameters_id=MA_PM25, limit=100)
    ds = []
    for loc in d.get("results", []):
        cb = [s for s in loc.get("sensors", []) if (s.get("parameter") or {}).get("id") == MA_PM25]
        if not cb or not loc.get("coordinates"):
            continue
        ds.append({"ma": loc["id"], "ten": loc.get("name") or f"OpenAQ {loc['id']}",
                   "nha_cung_cap": (loc.get("provider") or {}).get("name"),
                   "la_cam_bien_re": not loc.get("isMonitor", False), "ma_cam_bien_pm25": cb[0]["id"],
                   "lat": loc["coordinates"]["latitude"], "lon": loc["coordinates"]["longitude"],
                   "tu": ((loc.get("datetimeFirst") or {}).get("local") or "")[:10],
                   "den": ((loc.get("datetimeLast") or {}).get("local") or "")[:10]})
    return ds


def tai_gio(ma_cam_bien: int, tu: date, den: date) -> pd.DataFrame:
    """Số liệu PM2.5 trung bình theo giờ của một cảm biến (đã gộp sẵn bởi OpenAQ), giờ Việt Nam."""
    hang, trang = [], 1
    while True:
        d = _goi(f"/sensors/{ma_cam_bien}/hours", datetime_from=f"{tu}T00:00:00Z", datetime_to=f"{den}T23:59:59Z",
                 limit=1000, page=trang)
        kq = d.get("results", [])
        for x in kq:
            v = x.get("value")
            t = ((x.get("period") or {}).get("datetimeFrom") or {}).get("utc")
            if v is not None and t and 0 <= v < 1000:          # loại giá trị âm / lỗi cảm biến
                hang.append((t, float(v)))
        if len(kq) < 1000:
            break
        trang += 1
    df = pd.DataFrame(hang, columns=["utc", "pm25"])
    if df.empty:
        return df.assign(thoi_gian=pd.Series(dtype="datetime64[ns]"))
    df["thoi_gian"] = pd.to_datetime(df["utc"], utc=True).dt.tz_convert("Asia/Bangkok").dt.tz_localize(None).dt.floor("h")
    return df.groupby("thoi_gian", as_index=False)["pm25"].mean()


def luu_csdl(engine, tram: dict, df: pd.DataFrame):
    from sqlalchemy import text
    with engine.begin() as c:
        for cau in DDL:
            c.execute(text(cau))
        c.execute(text("""
            INSERT INTO tram_do_that (ma, ten, nha_cung_cap, la_cam_bien_re, ma_cam_bien_pm25, toado)
            VALUES (:ma, :ten, :ncc, :re, :cb, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))
            ON CONFLICT (ma) DO UPDATE SET ten = EXCLUDED.ten, nha_cung_cap = EXCLUDED.nha_cung_cap,
                la_cam_bien_re = EXCLUDED.la_cam_bien_re, ma_cam_bien_pm25 = EXCLUDED.ma_cam_bien_pm25,
                toado = EXCLUDED.toado, cap_nhat = NOW()
        """), {"ma": tram["ma"], "ten": tram["ten"], "ncc": tram["nha_cung_cap"], "re": tram["la_cam_bien_re"],
               "cb": tram["ma_cam_bien_pm25"], "lat": tram["lat"], "lon": tram["lon"]})
        if not df.empty:
            c.execute(text("""
                INSERT INTO do_that_gio (ma_tram, gio, pm25) VALUES (:m, :g, :v)
                ON CONFLICT (ma_tram, gio) DO UPDATE SET pm25 = EXCLUDED.pm25
            """), [{"m": tram["ma"], "g": r.thoi_gian.to_pydatetime(), "v": r.pm25} for r in df.itertuples()])


def tai_cams_gio(lat, lon, tu: date, den: date) -> pd.DataFrame:
    """PM2.5 theo giờ của mô hình CAMS (Open-Meteo) tại đúng vị trí trạm đo."""
    phan = []
    cur = tu
    while cur <= den:
        ket = min(cur + timedelta(days=90), den)
        r = requests.get("https://air-quality-api.open-meteo.com/v1/air-quality", timeout=60, params={
            "latitude": lat, "longitude": lon, "hourly": "pm2_5", "start_date": cur.isoformat(), "end_date": ket.isoformat(),
            "timezone": "Asia/Bangkok"}).json()
        phan.append(pd.DataFrame({"thoi_gian": pd.to_datetime(r["hourly"]["time"]), "cams": r["hourly"]["pm2_5"]}))
        cur = ket + timedelta(days=1)
        time.sleep(1)
    return pd.concat(phan, ignore_index=True).dropna()


def doi_chieu(tram: dict, that: pd.DataFrame, cams: pd.DataFrame) -> dict | None:
    from doi_chieu_tram_that import so_sanh, trung_binh_ngay
    g = that.merge(cams, on="thoi_gian").dropna()
    if len(g) < 48:
        return None
    sai = g["cams"] - g["pm25"]
    a, b = np.polyfit(g["cams"], g["pm25"], 1)          # hiệu chỉnh tuyến tính: đo_thật ≈ a·CAMS + b
    ngay = None
    try:
        ngay = so_sanh(trung_binh_ngay(that, "thoi_gian", "pm25"), trung_binh_ngay(cams.rename(columns={"cams": "pm25"}), "thoi_gian", "pm25"))
    except ValueError:
        pass
    return {"tram": {k: tram[k] for k in ("ma", "ten", "nha_cung_cap", "la_cam_bien_re", "lat", "lon")},
            "theo_gio": {"so_gio": int(len(g)), "tu": str(g["thoi_gian"].min()), "den": str(g["thoi_gian"].max()),
                         "tb_do_that": round(float(g["pm25"].mean()), 2), "tb_cams": round(float(g["cams"].mean()), 2),
                         "bias_cams_tru_that": round(float(sai.mean()), 2), "MAE": round(float(sai.abs().mean()), 2),
                         "RMSE": round(float(np.sqrt((sai ** 2).mean())), 2), "pearson_r": round(float(g["pm25"].corr(g["cams"])), 3),
                         "hieu_chinh": {"he_so": round(float(a), 4), "chan": round(float(b), 3)}},
            "theo_ngay": ngay}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    _nap_env()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--liet-ke", action="store_true")
    ap.add_argument("--tu", default=(date.today() - timedelta(days=365)).isoformat())
    ap.add_argument("--den", default=date.today().isoformat())
    ap.add_argument("--tram", help="danh sách mã location OpenAQ, cách nhau dấu phẩy")
    a = ap.parse_args()

    ds = tim_tram()
    print(f"Tìm thấy {len(ds)} trạm đo PM2.5 trong {BAN_KINH_M // 1000} km quanh trung tâm TP.HCM:")
    for t in ds:
        print(f"  {t['ma']:>8}  {t['ten'][:40]:<40} {('cảm biến giá rẻ' if t['la_cam_bien_re'] else 'trạm chuẩn'):<16} "
              f"{t['nha_cung_cap'] or '':<18} {t['tu']} → {t['den']}")
    if a.liet_ke or not ds:
        return
    if a.tram:
        chon = {int(x) for x in a.tram.split(",")}
        ds = [t for t in ds if t["ma"] in chon]

    from db_url import get_engine
    engine = get_engine()
    tu, den = date.fromisoformat(a.tu), date.fromisoformat(a.den)
    THU_MUC.mkdir(parents=True, exist_ok=True)
    ket_qua = []
    for t in ds:
        print(f"\n[{t['ma']}] {t['ten']}: tải {tu} → {den} ...", flush=True)
        df = tai_gio(t["ma_cam_bien_pm25"], tu, den)
        print(f"  {len(df):,} giờ có số liệu")
        if df.empty:
            continue
        luu_csdl(engine, t, df)
        df[["thoi_gian", "pm25"]].to_csv(THU_MUC / f"{t['ma']}.csv", index=False)
        cams = tai_cams_gio(t["lat"], t["lon"], df["thoi_gian"].min().date(), df["thoi_gian"].max().date())
        dc = doi_chieu(t, df, cams)
        if dc:
            h = dc["theo_gio"]
            print(f"  Đối chiếu {h['so_gio']:,} giờ: đo thật TB {h['tb_do_that']} · CAMS TB {h['tb_cams']} · "
                  f"bias {h['bias_cams_tru_that']:+} · MAE {h['MAE']} · r = {h['pearson_r']}")
            ket_qua.append(dc)
    if ket_qua:
        ra = GOC / "models" / "doi_chieu_tram_that.json"
        ra.write_text(json.dumps({"cap_nhat": datetime.now(timezone.utc).isoformat(timespec="seconds"), "nguon": "OpenAQ v3",
                                  "tram": ket_qua}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nĐã ghi {ra.relative_to(GOC)}")


if __name__ == "__main__":
    main()
