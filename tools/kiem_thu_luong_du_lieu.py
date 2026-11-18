"""Kiểm thử ĐẦU-CUỐI các luồng dữ liệu của AirHCM trên máy chủ đang chạy (khác tests/: dùng CSDL và mạng thật).

    python tools/kiem_thu_luong_du_lieu.py                          # máy chủ http://127.0.0.1:8000
    python tools/kiem_thu_luong_du_lieu.py --may-chu https://ten-mien # máy chủ đã triển khai
    python tools/kiem_thu_luong_du_lieu.py --dong-bo-that           # chạy thêm 1 lần đồng bộ thật (tải Open-Meteo + GEE)

Luồng được kiểm (không gửi email, không ghi đè số liệu thật):
  1. Nguồn ngoài   : Open-Meteo (CAMS + ERA5) trả số liệu; khóa Google Earth Engine sẵn sàng
  2. Lưu trữ        : CSDL có số liệu mới (độ trễ theo ngày), không có giá trị âm/trùng, lịch sử đồng bộ gần nhất
  3. Đồng bộ        : data_pipeline/dong_bo_hang_ngay.py tính đúng khoảng ngày cần tải bù (--kiem-tra)
  4. API → giao diện : các API chính trả dữ liệu; AQI trên trang Tổng quan khớp công thức VN_AQI tính lại độc lập
  5. CDC            : thay đổi trong CSDL → PostgreSQL NOTIFY → bus sự kiện → nhật ký hệ thống
Mã thoát 0 = mọi luồng đạt.
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

GOC = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(GOC / "backend"), str(GOC / "ml"), str(GOC / "data_pipeline")]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
KQ = []


def ghi(trang_thai, luong, noi_dung):
    KQ.append((trang_thai, luong))
    print(f"  [{trang_thai:<4}] {noi_dung}")


def tieu_de(s):
    print(f"\n{s}")


# ---------------------------------------------------------------- 1. Nguồn dữ liệu ngoài
def luong_nguon_ngoai(kiem_gee: bool):
    tieu_de("1. Nguồn dữ liệu ngoài")
    hom_qua = (date.today() - timedelta(days=1)).isoformat()
    try:
        t0 = time.time()
        r = requests.get("https://air-quality-api.open-meteo.com/v1/air-quality", timeout=30, params={
            "latitude": 10.7769, "longitude": 106.7009, "hourly": "pm2_5,pm10,ozone", "start_date": hom_qua,
            "end_date": hom_qua, "timezone": "Asia/Bangkok"}).json()
        gt = [x for x in r["hourly"]["pm2_5"] if x is not None]
        ghi("ĐẠT" if len(gt) >= 20 else "LỖI", "nguon", f"Open-Meteo CAMS: {len(gt)}/24 giờ ngày {hom_qua}, "
            f"PM2.5 TB {sum(gt) / max(len(gt), 1):.1f} µg/m³ ({time.time() - t0:.1f}s)")
    except Exception as e:
        ghi("LỖI", "nguon", f"Open-Meteo không phản hồi: {type(e).__name__}: {e}")
    try:
        from download_gee_data import KEY_FILE, SERVICE_ACCOUNT
        if not Path(KEY_FILE).exists():
            ghi("CẢNH", "nguon", f"Chưa có khóa GEE ({Path(KEY_FILE).name}): đồng bộ vệ tinh sẽ bị bỏ qua")
        elif kiem_gee:
            import ee
            t0 = time.time()
            ee.Initialize(ee.ServiceAccountCredentials(SERVICE_ACCOUNT, KEY_FILE))
            n = ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_NO2").filterDate(
                (date.today() - timedelta(days=30)).isoformat(), date.today().isoformat()).size().getInfo()
            ghi("ĐẠT", "nguon", f"Google Earth Engine: đăng nhập được, {n} ảnh NO₂ Sentinel-5P trong 30 ngày ({time.time() - t0:.1f}s)")
        else:
            ghi("ĐẠT", "nguon", "Khóa GEE có sẵn (thêm --gee để thử đăng nhập Earth Engine thật)")
    except Exception as e:
        ghi("LỖI", "nguon", f"Google Earth Engine: {type(e).__name__}: {str(e)[:150]}")


# ---------------------------------------------------------------- 2. Lưu trữ
def luong_luu_tru():
    tieu_de("2. Lưu trữ (PostgreSQL/PostGIS)")
    from database import engine
    from sqlalchemy import text
    with engine.connect() as c:
        moi = c.execute(text("SELECT max(ngay_do), count(*), count(DISTINCT tram_id) FROM du_lieu_tram_mat_dat")).fetchone()
        tre = (date.today() - moi[0]).days if moi[0] else 999
        ghi("ĐẠT" if tre <= 3 else "CẢNH" if tre <= 7 else "LỖI", "luu_tru",
            f"Số liệu trạm: {moi[1]:,} dòng, {moi[2]} trạm, mới nhất {moi[0]} (trễ {tre} ngày; CAMS/ERA5 trễ 1–3 ngày là bình thường)")
        g = c.execute(text("SELECT max(ngay_do), count(*) FROM du_lieu_gee_tphcm")).fetchone()
        tre_g = (date.today() - g[0]).days if g[0] else 999
        ghi("ĐẠT" if tre_g <= 21 else "CẢNH", "luu_tru", f"Số liệu vệ tinh: {g[1]:,} dòng, mới nhất {g[0]} (trễ {tre_g} ngày; Sentinel-5P OFFL trễ ~1–2 tuần)")
        am = c.execute(text("SELECT count(*) FROM du_lieu_tram_mat_dat WHERE pm25_mean < 0 OR pm10_mean < 0 OR o3_mean < 0")).scalar()
        trung = c.execute(text("SELECT count(*) FROM (SELECT tram_id, ngay_do FROM du_lieu_tram_mat_dat GROUP BY 1, 2 HAVING count(*) > 1) x")).scalar()
        ghi("ĐẠT" if am == 0 and trung == 0 else "LỖI", "luu_tru", f"Chất lượng: {am} giá trị âm, {trung} cặp (trạm, ngày) bị trùng")
        ls = c.execute(text("SELECT bat_dau, trang_thai, nguon_kich_hoat, so_dong_openmeteo, so_dong_gee, ghi_chu "
                            "FROM lich_su_dong_bo ORDER BY bat_dau DESC LIMIT 1")).fetchone()
        if ls:
            gio = (datetime.now(ls.bat_dau.tzinfo) - ls.bat_dau).total_seconds() / 3600 if ls.bat_dau.tzinfo else \
                (datetime.now() - ls.bat_dau).total_seconds() / 3600
            ghi("ĐẠT" if ls.trang_thai in ("thanh_cong", "khong_can") and gio < 36 else "CẢNH", "luu_tru",
                f"Đồng bộ gần nhất: {ls.bat_dau:%d/%m %H:%M} ({gio:.0f} giờ trước) · {ls.trang_thai} · kích hoạt bởi {ls.nguon_kich_hoat} · "
                f"+{ls.so_dong_openmeteo or 0} dòng Open-Meteo, +{ls.so_dong_gee or 0} dòng GEE")
        else:
            ghi("CẢNH", "luu_tru", "Chưa có lần đồng bộ nào trong lich_su_dong_bo")


# ---------------------------------------------------------------- 3. Đồng bộ
def luong_dong_bo(that: bool):
    tieu_de("3. Đồng bộ tự động (data_pipeline/dong_bo_hang_ngay.py)")
    lenh = [sys.executable, str(GOC / "data_pipeline" / "dong_bo_hang_ngay.py"), "--nguon", "kiem_thu"] + ([] if that else ["--kiem-tra"])
    t0 = time.time()
    p = subprocess.run(lenh, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    dong = [d for d in (p.stdout + p.stderr).splitlines() if d.strip()]
    for d in dong[-6:]:
        print("         │ " + d[:150])
    ma = {0: ("ĐẠT", "thành công / không có gì cần tải"), 1: ("CẢNH", "một phần lỗi"), 2: ("LỖI", "lỗi"),
          3: ("CẢNH", "đang có lần chạy khác")}.get(p.returncode, ("LỖI", f"mã {p.returncode}"))
    ghi(ma[0], "dong_bo", f"{'Chạy đồng bộ thật' if that else 'Tính khoảng ngày cần tải (--kiem-tra)'}: {ma[1]} ({time.time() - t0:.0f}s)")


# ---------------------------------------------------------------- 4. API
def luong_api(B: str):
    tieu_de(f"4. API → giao diện ({B})")
    from tinh_aqi import tinh_aqi_tong_hop
    s = requests.Session()
    r = s.get(B + "/api/v1/health", timeout=10)
    ghi("ĐẠT" if r.status_code == 200 and r.json().get("csdl") else "LỖI", "api", f"Health: {r.status_code} {r.text[:120]}")
    for duong, mo_ta in [("/api/v1/du-bao-gio", "Dự báo 24 giờ"), ("/api/v1/aqi-tat-ca-tram", "AQI các trạm"),
                         ("/api/v1/dong-bo/trang-thai", "Trạng thái đồng bộ"),
                         ("/api/v1/day/aqi-hien-tai", "AQI gọn cho app chạy nền"), ("/sitemap.xml", "Sitemap SEO")]:
        try:
            t0 = time.time(); r = s.get(B + duong, timeout=60)
            ghi("ĐẠT" if r.status_code == 200 and len(r.content) > 20 else "LỖI", "api",
                f"{mo_ta:<26} {duong:<28} {r.status_code} · {len(r.content):>7,} byte · {1000 * (time.time() - t0):.0f} ms")
        except Exception as e:
            ghi("LỖI", "api", f"{mo_ta}: {type(e).__name__}: {e}")
    tq = s.get(B + "/api/v1/tong-quan", timeout=60).json()["hien_tai"]
    aqi_tinh, chat = tinh_aqi_tong_hop(pm25=tq.get("pm25"), pm10=tq.get("pm10"), o3=tq.get("o3"))
    # Số liệu hiển thị đã làm tròn 1 chữ số → cho lệch ±2 điểm AQI do làm tròn
    khop = aqi_tinh is not None and tq.get("aqi") is not None and abs(aqi_tinh - tq["aqi"]) <= 2
    ghi("ĐẠT" if khop else "CẢNH", "api", f"Tổng quan: AQI {tq.get('aqi')} ({tq.get('muc')}, chất chính {tq.get('chat')}) · tính lại độc lập "
        f"từ PM2.5={tq.get('pm25')}, PM10={tq.get('pm10')}, O₃={tq.get('o3')} → {aqi_tinh} ({chat})")
    gon = s.get(B + "/api/v1/day/aqi-hien-tai", timeout=30).json()
    ghi("ĐẠT" if gon.get("aqi") == tq.get("aqi") else "LỖI", "api", f"API gọn của app khớp trang Tổng quan: {gon.get('aqi')} = {tq.get('aqi')}")


# ---------------------------------------------------------------- 5. CDC: CSDL → NOTIFY → bus sự kiện
def luong_cdc():
    tieu_de("5. CDC: thay đổi CSDL → PostgreSQL NOTIFY → bus sự kiện → nhật ký")
    from database import engine
    from sqlalchemy import text
    with engine.begin() as c:
        moc = c.execute(text("SELECT LOCALTIMESTAMP")).scalar()   # cùng kiểu với cột thoi_gian (TIMESTAMP không múi giờ)
        tram = c.execute(text("SELECT id, ma_tram FROM tram_quan_trac ORDER BY id LIMIT 1")).fetchone()
        if not tram:
            ghi("CẢNH", "cdc", "Chưa có trạm nào để thử"); return
        # Cập nhật không đổi giá trị: trigger vẫn phát NOTIFY, dữ liệu không thay đổi, không kích hoạt gửi email
        c.execute(text("UPDATE tram_quan_trac SET ten_tram = ten_tram WHERE id = :i"), {"i": tram.id})
    for _ in range(20):
        time.sleep(0.5)
        with engine.connect() as c:
            r = c.execute(text("SELECT thoi_gian, noi_dung FROM nhat_ky_he_thong WHERE nguon = 'cdc' AND thoi_gian >= :m "
                               "ORDER BY thoi_gian DESC LIMIT 1"), {"m": moc}).fetchone()
        if r:
            ghi("ĐẠT", "cdc", f"Trigger → NOTIFY → máy chủ ghi nhật ký sau {(r.thoi_gian - moc).total_seconds() * 1000:.0f} ms: “{r.noi_dung}”")
            return
    ghi("LỖI", "cdc", f"Không thấy sự kiện CDC cho trạm {tram.ma_tram} sau 10 giây (máy chủ có đang chạy và nối cùng CSDL?)")


def main():
    ap = argparse.ArgumentParser(description="Kiểm thử đầu-cuối các luồng dữ liệu AirHCM")
    ap.add_argument("--may-chu", default="http://127.0.0.1:8000")
    ap.add_argument("--dong-bo-that", action="store_true", help="chạy 1 lần đồng bộ thật (tải và ghi số liệu mới)")
    ap.add_argument("--gee", action="store_true", help="thử đăng nhập Google Earth Engine thật")
    a = ap.parse_args()
    B = a.may_chu.rstrip("/")
    print(f"Kiểm thử luồng dữ liệu AirHCM · {datetime.now():%d/%m/%Y %H:%M} · máy chủ {B}")
    for ham in (lambda: luong_nguon_ngoai(a.gee), luong_luu_tru, lambda: luong_dong_bo(a.dong_bo_that),
                lambda: luong_api(B), luong_cdc):
        try:
            ham()
        except Exception as e:
            ghi("LỖI", "?", f"{type(e).__name__}: {e}")
    loi = sum(1 for t, _ in KQ if t == "LỖI"); cb = sum(1 for t, _ in KQ if t == "CẢNH")
    print(f"\nTổng: {len(KQ)} mục · {len(KQ) - loi - cb} đạt · {cb} cảnh báo · {loi} lỗi")
    return 1 if loi else 0


if __name__ == "__main__":
    sys.exit(main())
