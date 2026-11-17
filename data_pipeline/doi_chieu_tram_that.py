"""Đối chiếu PM2.5 của mô hình CAMS (Open-Meteo) với số liệu ĐO THỰC TẾ tại một trạm.

Đây là bằng chứng mà báo cáo còn thiếu: nhãn PM2.5 của đồ án là đầu ra mô hình CAMS, không phải đo đạc.
Script tính sai lệch trung bình (bias), MAE, RMSE, hệ số tương quan Pearson theo NGÀY, và mức khớp khi so với ngưỡng
QCVN 50 / WHO 15 µg/m³ (TB 24 giờ). Kết quả cho biết CAMS "gần không khí thật" tới đâu — đây là giới hạn trần
của mọi mô hình học CAMS.

Chạy từ THƯ MỤC GỐC dự án. Hai cách cấp số liệu đo:
  A) File CSV của bạn (xuất từ OpenAQ/AirNow/trạm quan trắc), cột: thoi_gian,pm25  (giờ hoặc ngày, múi giờ địa phương hoặc ISO)
       python data_pipeline/doi_chieu_tram_that.py --csv du_lieu/tram_that.csv --lat 10.78 --lon 106.70
  B) Tải từ OpenAQ v3 (cần khóa API miễn phí ở https://explore.openaq.org, đặt biến OPENAQ_API_KEY; cần mã sensor PM2.5 của trạm):
       python data_pipeline/doi_chieu_tram_that.py --openaq-sensor 12345 --tu 2025-01-01 --den 2025-12-31 --lat 10.78 --lon 106.70
     (Phần tải OpenAQ viết theo tài liệu API v3, CHƯA được kiểm thử với máy chủ thật; nếu lỗi, dùng cách A.)
Ghi chú: lat/lon phải là vị trí của TRẠM ĐO, vì CAMS là lưới ~0,4° (~45 km) còn trạm là một điểm: sai lệch một phần do khác thang không gian.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

NGUONG = {"QCVN_05_2023": 50.0, "WHO_2021": 15.0}


def trung_binh_ngay(df, cot_gio="thoi_gian", cot_gt="pm25", toi_thieu_gio=18):
    """Trung bình ngày; ngày có ít hơn `toi_thieu_gio` giờ bị loại nếu dữ liệu là theo giờ."""
    d = df.copy()
    d[cot_gio] = pd.to_datetime(d[cot_gio])
    if getattr(d[cot_gio].dt, "tz", None) is not None:
        d[cot_gio] = d[cot_gio].dt.tz_convert("Asia/Bangkok").dt.tz_localize(None)
    d["ngay"] = d[cot_gio].dt.normalize()
    g = d.groupby("ngay")[cot_gt].agg(["mean", "count"])
    theo_gio = (d.groupby("ngay")[cot_gio].nunique().median() or 1) > 1
    if theo_gio:
        g = g[g["count"] >= toi_thieu_gio]
    return g["mean"].rename(cot_gt)


def so_sanh(do_that: pd.Series, cams: pd.Series):
    """Hai chuỗi theo ngày (index = ngày). Trả về dict chỉ số; do_that là 'chân lý'."""
    d = pd.concat([do_that.rename("that"), cams.rename("cams")], axis=1).dropna()
    n = len(d)
    if n < 10:
        raise ValueError(f"Chỉ có {n} ngày trùng nhau; cần tối thiểu 10 để đối chiếu.")
    sai = d["cams"] - d["that"]
    kq = {"so_ngay": int(n), "tu": str(d.index.min().date()), "den": str(d.index.max().date()),
          "tb_do_that": float(d["that"].mean()), "tb_cams": float(d["cams"].mean()),
          "bias_cams_tru_that": float(sai.mean()), "MAE": float(sai.abs().mean()),
          "RMSE": float(np.sqrt((sai ** 2).mean())), "pearson_r": float(d["that"].corr(d["cams"])),
          "ti_le_bias_so_voi_tb_that": float(sai.mean() / d["that"].mean())}
    kq["ngưỡng"] = {}
    for ten, nguong in NGUONG.items():
        a, b = d["that"] > nguong, d["cams"] > nguong
        kq["ngưỡng"][ten] = {"so_ngay_that_vuot": int(a.sum()), "so_ngay_cams_vuot": int(b.sum()),
                             "ti_le_phan_loai_dung": float((a == b).mean()),
                             "bo_sot": int((a & ~b).sum()), "bao_nham": int((~a & b).sum())}
    kq["dien_giai"] = ("CAMS " + ("CAO hơn" if sai.mean() > 0 else "THẤP hơn") +
                       f" số đo thật trung bình {abs(sai.mean()):.1f} µg/m³; sai số tuyệt đối trung bình {sai.abs().mean():.1f}; "
                       f"tương quan r = {d['that'].corr(d['cams']):.2f}. Mô hình học máy huấn luyện trên CAMS thừa hưởng sai lệch này.")
    return kq


def tai_cams(lat, lon, tu, den):
    import requests
    cac, cur = [], pd.Timestamp(tu)
    ket_thuc = pd.Timestamp(den)
    while cur <= ket_thuc:
        ket = min(cur + pd.Timedelta(days=179), ket_thuc)
        for thu in range(4):
            r = requests.get("https://air-quality-api.open-meteo.com/v1/air-quality", params={
                "latitude": lat, "longitude": lon, "hourly": "pm2_5", "start_date": cur.date().isoformat(),
                "end_date": ket.date().isoformat(), "timezone": "Asia/Bangkok"}, timeout=60)
            if r.status_code == 429:
                time.sleep(15 * (thu + 1)); continue
            r.raise_for_status(); break
        h = r.json()["hourly"]
        cac.append(pd.DataFrame({"thoi_gian": h["time"], "pm25": h["pm2_5"]}))
        cur = ket + pd.Timedelta(days=1); time.sleep(1.5)
    return pd.concat(cac, ignore_index=True)


def tai_openaq(sensor, tu, den):
    """OpenAQ v3: /v3/sensors/{id}/hours. CHƯA kiểm thử với máy chủ thật."""
    import requests
    khoa = os.getenv("OPENAQ_API_KEY")
    if not khoa:
        sys.exit("Thiếu biến môi trường OPENAQ_API_KEY.")
    rows, trang = [], 1
    while True:
        r = requests.get(f"https://api.openaq.org/v3/sensors/{sensor}/hours", headers={"X-API-Key": khoa}, params={
            "datetime_from": f"{tu}T00:00:00Z", "datetime_to": f"{den}T23:59:59Z", "limit": 1000, "page": trang}, timeout=60)
        r.raise_for_status()
        kq = r.json().get("results", [])
        if not kq:
            break
        for x in kq:
            rows.append({"thoi_gian": x["period"]["datetimeFrom"]["utc"], "pm25": x["value"]})
        trang += 1; time.sleep(1)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv"); ap.add_argument("--openaq-sensor")
    ap.add_argument("--tu"); ap.add_argument("--den")
    ap.add_argument("--lat", type=float, required=True); ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--ra", default="models/doi_chieu_tram_that.json")
    a = ap.parse_args()
    if a.csv:
        that = pd.read_csv(a.csv)
    elif a.openaq_sensor and a.tu and a.den:
        that = tai_openaq(a.openaq_sensor, a.tu, a.den)
    else:
        sys.exit("Cần --csv, hoặc --openaq-sensor kèm --tu và --den.")
    that = that[that["pm25"].between(0, 1000)]          # bỏ giá trị lỗi/âm của cảm biến
    ngay_that = trung_binh_ngay(that)
    cams = trung_binh_ngay(tai_cams(a.lat, a.lon, ngay_that.index.min().date(), ngay_that.index.max().date()), toi_thieu_gio=18)
    kq = so_sanh(ngay_that, cams)
    Path(a.ra).parent.mkdir(exist_ok=True)
    Path(a.ra).write_text(json.dumps(kq, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(kq, ensure_ascii=False, indent=2)); print(f"\nĐã lưu {a.ra}")


if __name__ == "__main__":
    main()
