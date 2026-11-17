"""Huấn luyện mô hình dự báo PM2.5 THEO GIỜ (1–24 giờ tới) và in kết quả đánh giá TRUNG THỰC.

Chạy từ THƯ MỤC GỐC dự án (nơi có backend/):
    python ml/train_du_bao_gio.py                      # tải dữ liệu giờ từ Open-Meteo rồi huấn luyện
    python ml/train_du_bao_gio.py --tu 2022-08-01      # đổi ngày bắt đầu
    python ml/train_du_bao_gio.py --csv du_lieu/gio_cache.csv   # dùng lại file đã tải, không gọi mạng

Kết quả: models/du_bao_gio.joblib và models/du_bao_gio_chi_so.json (trang Dự báo đọc 2 file này).
Số liệu gốc là PM2.5/PM10 của mô hình CAMS và thời tiết ERA5 qua Open-Meteo, KHÔNG phải đo đạc mặt đất.
"""

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC / "backend"))

import pandas as pd
import requests

LAT, LON = 10.7769, 106.7009


def _get(url, params, thu=4):
    for i in range(thu):
        r = requests.get(url, params=params, timeout=60)
        if r.status_code == 429:
            time.sleep(15 * (i + 1))
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("Open-Meteo từ chối do giới hạn tốc độ. Chờ vài phút rồi chạy lại.")


def tai_du_lieu(tu: date, den: date) -> pd.DataFrame:
    cac = []
    cur = tu
    while cur <= den:
        ket = min(cur + timedelta(days=179), den)
        print(f"  Đang tải {cur} → {ket} ...")
        aq = _get("https://air-quality-api.open-meteo.com/v1/air-quality", {
            "latitude": LAT, "longitude": LON, "hourly": "pm2_5,pm10", "start_date": cur.isoformat(), "end_date": ket.isoformat(),
            "timezone": "Asia/Bangkok"})
        th = _get("https://archive-api.open-meteo.com/v1/archive", {
            "latitude": LAT, "longitude": LON, "start_date": cur.isoformat(), "end_date": ket.isoformat(),
            "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation,surface_pressure", "timezone": "Asia/Bangkok"})
        a = pd.DataFrame(aq["hourly"]); t = pd.DataFrame(th["hourly"])
        cac.append(a.merge(t, on="time", how="left"))
        cur = ket + timedelta(days=1)
        time.sleep(1.5)
    return pd.concat(cac, ignore_index=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tu", default="2022-08-01", help="Ngày bắt đầu (CAMS toàn cầu có từ 08/2022)")
    ap.add_argument("--den", default=None, help="Ngày kết thúc (mặc định: hôm nay − 6 ngày vì ERA5 có độ trễ)")
    ap.add_argument("--csv", default=None, help="Dùng file CSV đã tải thay vì gọi Open-Meteo")
    a = ap.parse_args()

    from services import du_bao_gio as dbg
    if a.csv:
        df = pd.read_csv(a.csv)
    else:
        den = date.fromisoformat(a.den) if a.den else date.today() - timedelta(days=6)
        print(f"Tải dữ liệu giờ {a.tu} → {den} (trung tâm TP.HCM)...")
        df = tai_du_lieu(date.fromisoformat(a.tu), den)
        dong = GOC / "du_lieu" / "gio_cache.csv"
        df.to_csv(dong, index=False)
        print(f"Đã lưu bản sao dữ liệu: {dong}")
    df = df[dbg.CAC_COT]
    print(f"Số dòng giờ: {len(df)}  ·  thiếu PM2.5: {int(df['pm2_5'].isna().sum())}")
    print("Đang đánh giá + huấn luyện (vài phút)...")
    kq = dbg.danh_gia_va_huan_luyen(df, luu=True)

    print("\n=== KẾT QUẢ TRÊN TẬP KIỂM TRA (20% cuối theo thời gian) ===")
    print(f"Mẫu: {kq['so_mau']}  ·  kiểm tra từ {kq['kiem_tra_tu']}")
    print(f"{'Bước (giờ)':>11} {'RMSE':>7} {'MAE':>7} {'R²':>7} {'RMSE persist.':>14} {'Kỹ năng':>9}")
    for h, m in kq["theo_buoc"].items():
        print(f"{h:>11} {m['rmse']:7.2f} {m['mae']:7.2f} {m['r2']:7.3f} {m['rmse_persistence']:14.2f} {m['ky_nang_so_voi_persistence']:9.3f}")
    t = kq["tong"]
    print(f"\nTổng 1–24 giờ: RMSE {t['rmse']:.2f}, R² {t['r2']:.3f}; persistence RMSE {t['rmse_persistence']:.2f}; "
          f"kỹ năng {t['ky_nang_so_voi_persistence']:.3f}")
    if t.get("rmse_hom_qua_cung_gio") is not None:
        print(f"Nền 'giống hôm qua cùng giờ': RMSE {t['rmse_hom_qua_cung_gio']:.2f}")
    if kq["kiem_tra_cheo"]:
        print("Kiểm tra chéo theo thời gian (kỹ năng): " + ", ".join(f"{c['ky_nang_so_voi_persistence']:.3f}" for c in kq["kiem_tra_cheo"]))
    print("\nĐọc kết quả: kỹ năng > 0 nghĩa là mô hình tốt hơn 'giữ nguyên PM2.5 hiện tại'. Nếu <= 0 ở bước xa, đừng khẳng định mô hình dự báo được.")
    print("Đã lưu models/du_bao_gio.joblib và models/du_bao_gio_chi_so.json")


if __name__ == "__main__":
    main()
