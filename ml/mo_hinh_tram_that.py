"""Mô hình dự báo PM2.5 THẬT (số đo trạm mặt đất) cho ngày mai, so sánh với dự báo dựa trên mô hình CAMS.

Vì sao: toàn bộ mô hình khác của AirHCM học nhãn từ CAMS (số liệu mô hình, lưới ~45 km). Đối chiếu với trạm thật cho thấy CAMS
khớp mức trung bình nhưng tương quan theo ngày thấp (r ≈ 0,2–0,3). Mô hình này học trực tiếp từ SỐ ĐO THẬT để trả lời câu hỏi
"dự báo không khí thật ngày mai được tới đâu?".

Dữ liệu (một điểm đo thật có chuỗi dài nhất, liên tục tới hiện tại): cảm biến AirGradient "CMT8" (OpenAQ, mã 3276359), quận 3 cũ.
- Nhãn y_t: PM2.5 trung bình ngày đo thật (chỉ dùng ngày có ≥ 18 giờ số liệu).
- CAMS_t: PM2.5 trung bình ngày của CAMS tại đúng tọa độ (Open-Meteo Air Quality).
- Thời tiết_t: ERA5 (Open-Meteo Archive) — nhiệt độ, độ ẩm, gió, mưa.
Dự báo ngày t+1 dùng: y_t, y_{t−1}, TB 7 ngày đo thật, CAMS_{t+1}, thời tiết_{t+1}, tháng.
GIỚI HẠN: khi đánh giá, CAMS_{t+1} và thời tiết_{t+1} là số liệu tái phân tích (đã biết), khi vận hành thật sẽ là DỰ BÁO của
CAMS/NWP (kém chính xác hơn) → kết quả đánh giá là cận trên lạc quan cho phần dùng CAMS/thời tiết.

So sánh (trên 30% thời gian cuối, mô hình chưa thấy):
  persistence "mai = hôm nay" · CAMS thô · CAMS cộng bù độ lệch (học trên tập huấn luyện) · hồi quy tuyến tính (Ridge) · Random Forest.
Chỉ số: MAE, RMSE, bias, r, kỹ năng = 1 − RMSE/RMSE_persistence (khoảng tin cậy 95% bootstrap theo khối 7 ngày), tách mùa khô (12–4)
và mùa mưa (5–11); phát hiện ngày vượt ngưỡng (QCVN 45, mức "Kém" 50): độ nhạy (recall), độ chính xác (precision), F1.

Chạy:  python ml/mo_hinh_tram_that.py   → models/mo_hinh_tram_that.json, models/du_bao_tram_that.joblib
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

GOC = Path(__file__).resolve().parent.parent
MA_TRAM, TEN_TRAM, LAT, LON = 3276359, "CMT8 (AirGradient, OpenAQ)", 10.78533, 106.67029
TEP_DO = GOC / "du_lieu" / "tram_that" / f"{MA_TRAM}.csv"
NGUONG = {"QCVN_45": 45.0, "Kem_50": 50.0}
DAC_TRUNG = ["y", "y_lag1", "y_tb7", "cams_mai", "nhiet_do_mai", "do_am_mai", "gio_mai", "mua_mai", "thang_sin", "thang_cos"]
SEED = 42


def ngay_do_that(tep=TEP_DO, toi_thieu_gio=18) -> pd.DataFrame:
    d = pd.read_csv(tep, parse_dates=["thoi_gian"])
    d["ngay"] = d["thoi_gian"].dt.normalize()
    g = d.groupby("ngay")["pm25"].agg(["mean", "count"])
    g = g[g["count"] >= toi_thieu_gio]
    return pd.DataFrame({"ngay": g.index, "y": g["mean"].values})


def tai_cams_thoi_tiet(tu, den, lat=LAT, lon=LON, get=requests.get) -> pd.DataFrame:
    """CAMS PM2.5 (TB ngày) + ERA5 thời tiết ngày tại tọa độ, chia đợt 90 ngày."""
    phan_aq, phan_tt = [], []
    cur = pd.Timestamp(tu)
    while cur <= pd.Timestamp(den):
        ket = min(cur + pd.Timedelta(days=89), pd.Timestamp(den))
        r = get("https://air-quality-api.open-meteo.com/v1/air-quality", timeout=60, params={
            "latitude": lat, "longitude": lon, "hourly": "pm2_5", "start_date": f"{cur:%Y-%m-%d}", "end_date": f"{ket:%Y-%m-%d}",
            "timezone": "Asia/Bangkok"}).json()["hourly"]
        h = pd.DataFrame({"t": pd.to_datetime(r["time"]), "cams": r["pm2_5"]})
        phan_aq.append(h.groupby(h["t"].dt.normalize())["cams"].mean())
        r = get("https://archive-api.open-meteo.com/v1/archive", timeout=60, params={
            "latitude": lat, "longitude": lon, "start_date": f"{cur:%Y-%m-%d}", "end_date": f"{ket:%Y-%m-%d}", "timezone": "Asia/Bangkok",
            "daily": "temperature_2m_mean,relative_humidity_2m_mean,wind_speed_10m_mean,precipitation_sum"}).json()["daily"]
        phan_tt.append(pd.DataFrame({"ngay": pd.to_datetime(r["time"]), "nhiet_do": r["temperature_2m_mean"],
                                     "do_am": r["relative_humidity_2m_mean"], "gio": r["wind_speed_10m_mean"], "mua": r["precipitation_sum"]}))
        cur = ket + pd.Timedelta(days=1)
        time.sleep(0.5)
    aq = pd.concat(phan_aq).rename_axis("ngay").reset_index()
    return aq.merge(pd.concat(phan_tt), on="ngay", how="outer")


def tao_bang(do: pd.DataFrame, ngoai: pd.DataFrame) -> pd.DataFrame:
    """Mỗi dòng = ngày t (đã đo xong), nhãn = y_{t+1}. Chỉ giữ khi t−1, t, t+1 liên tục."""
    lich = pd.DataFrame({"ngay": pd.date_range(do["ngay"].min(), do["ngay"].max(), freq="D")})
    b = lich.merge(do, on="ngay", how="left").merge(ngoai, on="ngay", how="left")
    b["y_lag1"] = b["y"].shift(1)
    b["y_tb7"] = b["y"].rolling(7, min_periods=5).mean()
    for c, m in (("cams", "cams_mai"), ("nhiet_do", "nhiet_do_mai"), ("do_am", "do_am_mai"), ("gio", "gio_mai"), ("mua", "mua_mai")):
        b[m] = b[c].shift(-1)
    b["cams_hom_nay"] = b["cams"]
    b["nhan"] = b["y"].shift(-1)
    b["ngay_du_bao"] = b["ngay"] + pd.Timedelta(days=1)
    thang = b["ngay_du_bao"].dt.month
    b["thang_sin"], b["thang_cos"] = np.sin(2 * np.pi * thang / 12), np.cos(2 * np.pi * thang / 12)
    return b.dropna(subset=DAC_TRUNG + ["nhan"]).reset_index(drop=True)


def _chi_so(y, p, base_rmse=None):
    e = p - y
    rmse = float(np.sqrt(np.mean(e ** 2)))
    kq = {"MAE": round(float(np.mean(np.abs(e))), 2), "RMSE": round(rmse, 2), "bias": round(float(np.mean(e)), 2),
          "r": round(float(np.corrcoef(y, p)[0, 1]), 3) if len(y) > 2 else None}
    if base_rmse:
        kq["ky_nang"] = round(1 - rmse / base_rmse, 3)
    return kq


def _ky_nang_ci(y, p, base, so_lan=2000, khoi=7, seed=SEED):
    """Khoảng tin cậy 95% của kỹ năng 1 − RMSE/RMSE_base bằng bootstrap theo khối liên tiếp `khoi` ngày (giữ phụ thuộc thời gian)."""
    rng = np.random.default_rng(seed)
    n = len(y); so_khoi = int(np.ceil(n / khoi)); dau = np.arange(0, n - khoi + 1)
    kq = []
    for _ in range(so_lan):
        idx = np.concatenate([np.arange(s, s + khoi) for s in rng.choice(dau, so_khoi)])[:n]
        r_m, r_b = np.sqrt(np.mean((p[idx] - y[idx]) ** 2)), np.sqrt(np.mean((base[idx] - y[idx]) ** 2))
        kq.append(1 - r_m / r_b)
    return {"thap": round(float(np.percentile(kq, 2.5)), 3), "cao": round(float(np.percentile(kq, 97.5)), 3)}


def _vuot(y, p, t):
    o, d = y > t, p > t
    tp, fp, fn = int((o & d).sum()), int((~o & d).sum()), int((o & ~d).sum())
    rec = tp / (tp + fn) if tp + fn else None
    pre = tp / (tp + fp) if tp + fp else None
    f1 = 2 * rec * pre / (rec + pre) if rec and pre else (0.0 if (rec is not None and pre is not None) else None)
    return {"so_ngay_vuot_that": int(o.sum()), "bat_dung": tp, "bo_sot": fn, "bao_nham": fp,
            "do_nhay": None if rec is None else round(rec, 3), "do_chinh_xac": None if pre is None else round(pre, 3),
            "F1": None if f1 is None else round(f1, 3)}


def danh_gia(bang: pd.DataFrame, ti_le_test=0.3):
    n_test = int(len(bang) * ti_le_test)
    tr, te = bang.iloc[:-n_test], bang.iloc[-n_test:]
    Xtr, Xte, ytr, yte = tr[DAC_TRUNG].values, te[DAC_TRUNG].values, tr["nhan"].values, te["nhan"].values
    bu = float((tr["nhan"] - tr["cams_mai"]).mean())                       # độ lệch trung bình học trên tập huấn luyện
    ridge = make_pipeline(StandardScaler(), Ridge(alpha=1.0)).fit(Xtr, ytr)
    rf = RandomForestRegressor(n_estimators=400, min_samples_leaf=5, max_features=0.6, random_state=SEED, n_jobs=-1).fit(Xtr, ytr)
    du_doan = {"Mai = hôm nay (đo thật)": te["y"].values, "CAMS thô": te["cams_mai"].values,
               "CAMS cộng bù độ lệch": te["cams_mai"].values + bu, "Hồi quy tuyến tính (Ridge)": ridge.predict(Xte),
               "Random Forest": rf.predict(Xte)}
    base = du_doan["Mai = hôm nay (đo thật)"]
    rmse_base = float(np.sqrt(np.mean((base - yte) ** 2)))
    mua = np.where(te["ngay_du_bao"].dt.month.isin([12, 1, 2, 3, 4]), "khô", "mưa")
    kq = {}
    for ten, p in du_doan.items():
        x = _chi_so(yte, p, rmse_base)
        if ten != "Mai = hôm nay (đo thật)":
            x["ky_nang_ci95"] = _ky_nang_ci(yte, p, base)
        x["theo_mua"] = {}
        for m in ("khô", "mưa"):
            k = mua == m
            if k.sum() >= 10:
                rb = float(np.sqrt(np.mean((base[k] - yte[k]) ** 2)))
                x["theo_mua"][m] = {"so_ngay": int(k.sum()), **_chi_so(yte[k], p[k], rb)}
        x["vuot_nguong"] = {t: _vuot(yte, p, v) for t, v in NGUONG.items()}
        kq[ten] = x
    tam_quan_trong = sorted(zip(DAC_TRUNG, rf.feature_importances_), key=lambda z: -z[1])
    return {"so_ngay": len(bang), "so_ngay_huan_luyen": len(tr), "so_ngay_kiem_tra": len(te),
            "kiem_tra_tu": str(te["ngay_du_bao"].iloc[0].date()), "kiem_tra_den": str(te["ngay_du_bao"].iloc[-1].date()),
            "do_lech_cams_tap_huan_luyen": round(bu, 2), "mo_hinh": kq,
            "tam_quan_trong_rf": [{"dac_trung": a, "muc": round(float(b), 3)} for a, b in tam_quan_trong]}, rf, bu


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not TEP_DO.exists():
        sys.exit(f"Chưa có {TEP_DO.relative_to(GOC)} — chạy trước: python data_pipeline/tai_tram_that.py --tram {MA_TRAM}")
    do = ngay_do_that()
    print(f"Số đo thật: {len(do)} ngày ({do['ngay'].min():%d/%m/%Y} → {do['ngay'].max():%d/%m/%Y}). Tải CAMS + ERA5…", flush=True)
    ngoai = tai_cams_thoi_tiet(do["ngay"].min(), do["ngay"].max() + pd.Timedelta(days=1))
    bang = tao_bang(do, ngoai)
    kq, rf, bu = danh_gia(bang)
    # Mô hình vận hành: huấn luyện lại trên toàn bộ dữ liệu
    rf_toan_bo = RandomForestRegressor(n_estimators=400, min_samples_leaf=5, max_features=0.6, random_state=SEED, n_jobs=-1)
    rf_toan_bo.fit(bang[DAC_TRUNG].values, bang["nhan"].values)
    sai_so = (bang["nhan"] - rf_toan_bo.oob_prediction_) if getattr(rf_toan_bo, "oob_score", False) else None
    joblib.dump({"mo_hinh": rf_toan_bo, "dac_trung": DAC_TRUNG, "do_lech_cams": float((bang["nhan"] - bang["cams_mai"]).mean()),
                 "tram": {"ma": MA_TRAM, "ten": TEN_TRAM, "lat": LAT, "lon": LON},
                 "huan_luyen_den": str(bang["ngay_du_bao"].iloc[-1].date())}, GOC / "models" / "du_bao_tram_that.joblib")
    kq.update({"tram": {"ma": MA_TRAM, "ten": TEN_TRAM, "lat": LAT, "lon": LON}, "dac_trung": DAC_TRUNG,
               "cap_nhat": datetime.now().isoformat(timespec="seconds"),
               "gioi_han": ["Một điểm đo duy nhất (cảm biến giá rẻ AirGradient, không phải trạm chuẩn) — chưa đại diện cho cả thành phố.",
                            "Khi đánh giá, CAMS và thời tiết ngày mai là số liệu tái phân tích (đã biết); khi vận hành là dự báo nên sai số lớn hơn.",
                            "Cảm biến quang học giá rẻ thường đo cao khi độ ẩm cao; chưa hiệu chỉnh theo trạm chuẩn."]})
    ra = GOC / "models" / "mo_hinh_tram_that.json"
    ra.write_text(json.dumps(kq, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Kiểm tra {kq['so_ngay_kiem_tra']} ngày ({kq['kiem_tra_tu']} → {kq['kiem_tra_den']}); CAMS lệch trên tập huấn luyện: {kq['do_lech_cams_tap_huan_luyen']:+}")
    for ten, x in kq["mo_hinh"].items():
        ci = x.get("ky_nang_ci95")
        print(f"  {ten:<30} MAE {x['MAE']:6.2f}  RMSE {x['RMSE']:6.2f}  bias {x['bias']:+6.2f}  r {x['r']}  kỹ năng {x.get('ky_nang')}"
              + (f"  CI95 [{ci['thap']}, {ci['cao']}]" if ci else "")
              + f"  | QCVN45 nhạy {x['vuot_nguong']['QCVN_45']['do_nhay']} (vượt thật {x['vuot_nguong']['QCVN_45']['so_ngay_vuot_that']})")
    print("Đã ghi", ra.relative_to(GOC), "và models/du_bao_tram_that.joblib")


if __name__ == "__main__":
    main()
