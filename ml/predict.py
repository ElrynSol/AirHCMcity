"""Dự báo PM2.5 THEO NGÀY (v3.7) — dùng mô hình "dự báo ngày mai" (chỉ PM2.5 quá khứ + lịch).

Khác bản cũ:
  * Không còn dùng NO2/O3/thời tiết của hôm nay làm đặc trưng của ngày mai (đó là "ước lượng trong ngày", không phải dự báo).
  * Đặc trưng được tạo bằng ĐÚNG hàm tao_dac_trung của train_model.py (không lệch giữa huấn luyện và vận hành).
  * Nếu dữ liệu CSDL cũ quá 1 ngày thì TRẢ LỖI thay vì dự báo bằng số liệu cũ gán nhãn "ngày mai".
  * Khoảng dự báo là phân vị 10–90% của sai số thực trên tập kiểm tra (không phải độ lệch chuẩn giữa các cây).
  * Kỹ năng so với "mai = hôm nay" được trả kèm; nếu khoảng tin cậy chứa 0 thì cờ co_ky_nang_y_nghia = False.
Giữ các khóa cũ (ngay_du_bao, pm25_du_bao, khoang_dao_dong, muc_do, model_r2) để router/giao diện cũ không vỡ.
"""

import math
import os
from datetime import date, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

import train_model as tm

GOC = Path(__file__).resolve().parent.parent
MODEL_DIR = GOC / "models"
CAC_COT = ["no2_mean", "co_gee", "so2_gee", "o3_mean", "nhiet_do_mean", "do_am_mean", "gio_toc_do_mean", "mua_tong"]


def _phan_loai(pm25):
    """Mức AQI theo PM2.5 TB 24 giờ, mốc nồng độ của QĐ 1459/QĐ-TCMT (25, 50, 80, 150, 250 µg/m³)."""
    for nguong, muc in ((25, "Tốt"), (50, "Trung bình"), (80, "Kém"), (150, "Xấu"), (250, "Rất xấu")):
        if pm25 <= nguong:
            return muc
    return "Nguy hại"


def load_model():
    f = MODEL_DIR / "random_forest_pm25_du_bao.pkl"
    if not f.exists():
        raise FileNotFoundError("Chưa có models/random_forest_pm25_du_bao.pkl. Chạy: python ml/train_model.py")
    return joblib.load(f), joblib.load(MODEL_DIR / "model_metadata.pkl")


def _doc_chuoi_pm25(so_ngay=60) -> pd.DataFrame:
    from dotenv import load_dotenv
    from sqlalchemy import create_engine
    from urllib.parse import quote_plus
    load_dotenv(GOC / ".env")
    g = os.getenv
    url = g("DATABASE_URL") or (f"postgresql://{g('DB_USER')}:{quote_plus(g('DB_PASS') or '')}@{g('DB_HOST')}:{g('DB_PORT')}/{g('DB_NAME')}")
    df = pd.read_sql(f"""SELECT ngay_do, AVG(pm25_mean) AS pm25_mean FROM du_lieu_tram_mat_dat
                         GROUP BY ngay_do ORDER BY ngay_do DESC LIMIT {int(so_ngay)}""", create_engine(url))
    df["ngay_do"] = pd.to_datetime(df["ngay_do"])
    return df.sort_values("ngay_do").reset_index(drop=True)


def _them_cot_thieu(df):
    d = df.copy()
    for c in CAC_COT:
        if c not in d:
            d[c] = np.nan       # mô hình dự báo không dùng các cột này; chỉ để hàm tao_dac_trung chạy được
    return d


TRE_TOI_DA = 7   # số ngày dữ liệu được phép trễ so với ngày hệ thống; khoảng trống được dự báo bù (đệ quy)


def du_bao_tu_chuoi(df, model, meta, so_ngay=1, hom_nay=None):
    """Hàm thuần (không đọc CSDL) để dễ kiểm thử. df: cột ngay_do, pm25_mean (nhiều ngày gần nhất).
    Trả dự báo cho `so_ngay` ngày LIỀN SAU NGÀY HỆ THỐNG `hom_nay` (hom_nay+1 … hom_nay+so_ngay).
    Nếu dữ liệu kết thúc trước hom_nay, các ngày ở giữa được dự báo bù trước (không trả về) — bac_du_bao cho biết
    mỗi ngày cách ngày dữ liệu thật cuối cùng bao nhiêu bước; chỉ bước 1 được kiểm chứng trên tập kiểm tra."""
    hom_nay = pd.Timestamp(hom_nay or date.today()).normalize()
    d = df.dropna(subset=["pm25_mean"]).sort_values("ngay_do").reset_index(drop=True)
    if len(d) < 8:
        return {"error": "Không đủ dữ liệu PM2.5 gần đây để dự báo (cần ít nhất 8 ngày)."}
    ngay_cuoi = d["ngay_do"].iloc[-1]
    tre = (hom_nay - ngay_cuoi).days
    if tre > TRE_TOI_DA:
        return {"error": f"Dữ liệu PM2.5 trong CSDL mới đến {ngay_cuoi.date()} (cũ {tre} ngày, quá {TRE_TOI_DA} ngày cho phép), "
                         "không thể dự báo một cách hợp lệ. Hãy cập nhật CSDL (Trạng thái dữ liệu → Đồng bộ ngay) "
                         "hoặc dùng dự báo theo giờ (/api/v1/du-bao-gio)."}
    so_buoc = max(0, tre) + int(so_ngay)
    cot = meta["features_du_bao_ngay_mai"]
    chuoi = d[["ngay_do", "pm25_mean"]].copy()
    dm = meta.get("du_bao_metrics", {})
    pv = dm.get("phan_vi_sai_so")
    cv_ci = (meta.get("danh_gia", {}).get("mo_hinh", {}).get("du_bao_ngay_mai", {})
             .get("kiem_cheo_cuon_chieu", {}).get("gop", {}).get("ci95"))
    co_y_nghia = bool(cv_ci and cv_ci["thap"] > 0)
    kq = []
    for i in range(so_buoc):
        ngay = chuoi["ngay_do"].iloc[-1] + timedelta(days=1)
        thu = pd.concat([chuoi, pd.DataFrame({"ngay_do": [ngay], "pm25_mean": [np.nan]})], ignore_index=True)
        f = tm.tao_dac_trung(_them_cot_thieu(thu)).iloc[-1]
        X = pd.DataFrame([f[cot].astype(float)])
        if X.isna().any().any():
            return {"error": "Thiếu số liệu PM2.5 trong 7 ngày gần nhất (có ngày trống) nên không tạo được đặc trưng."}
        p = float(model.predict(X)[0])
        chuoi = pd.concat([chuoi, pd.DataFrame({"ngay_do": [ngay], "pm25_mean": [p]})], ignore_index=True)
        if ngay <= hom_nay:
            continue   # ngày bù khoảng trống giữa dữ liệu cuối và ngày hệ thống: dùng làm đầu vào, không trả về
        muc = {"ngay": str(ngay.date()), "pm25": round(p, 2), "muc_do": _phan_loai(p), "bac_du_bao": i + 1,
               "da_kiem_chung": i == 0}   # chỉ bước 1 (từ dữ liệu thật) được đánh giá; các bước sau suy ra đệ quy
        if pv:
            # Khoảng 80% của bước 1; các bước sau sai số cộng dồn nên nới rộng theo √bước (giả định sai số độc lập — ước lượng thô)
            k = math.sqrt(i + 1)
            muc["khoang_80"] = {"thap": round(max(p + pv["q10"] * k, 0), 2), "cao": round(p + pv["q90"] * k, 2)}
            muc["xac_suat_vuot"] = xac_suat_vuot(p, pv, k)
        kq.append(muc)
    return kq, {"ngay_du_lieu_cuoi": str(ngay_cuoi.date()), "pm25_hom_nay_nen": float(d["pm25_mean"].iloc[-1]),
                "ngay_he_thong": str(hom_nay.date()), "so_ngay_bu": max(0, tre),
                "model_r2": dm.get("R2"), "ky_nang": dm.get("ky_nang_so_voi_hom_qua"), "co_y_nghia": co_y_nghia, "pv": pv}


def xac_suat_vuot(p, pv, k=1.0):
    """Xác suất PM2.5 TB 24 giờ thực tế vượt ngưỡng WHO (15) và QCVN 05:2023 (45 từ 2026), từ dự báo điểm p và phân vị sai số
    q10/q90 trên tập kiểm tra. GIẢ ĐỊNH sai số phân phối chuẩn: μ = (q10+q90)/2, σ = (q90−q10)/(2·1,2816), nới theo k = √bước.
    Đây là ước lượng có tham số; độ tin cậy cần kiểm bằng Brier score / reliability trên tập kiểm tra (ml/danh_gia_xac_suat.py)."""
    mu = (pv["q10"] + pv["q90"]) / 2
    sd = max((pv["q90"] - pv["q10"]) / (2 * 1.2816), 1e-6) * k
    phi = lambda z: 0.5 * (1 + math.erf(z / math.sqrt(2)))
    return {"who_15": round(1 - phi((15.0 - p - mu) / sd), 3), "qcvn_45": round(1 - phi((45.0 - p - mu) / sd), 3)}


GHI_CHU = ("Kỹ năng của mô hình theo ngày so với mô hình nền 'mai = hôm nay' chưa khác biệt có ý nghĩa thống kê "
           "(khoảng tin cậy 95% chứa 0); dự báo theo giờ là sản phẩm dự báo chính. Nhãn PM2.5 là số liệu tái phân tích CAMS.")


def predict_next_day(gee_overrides=None):
    """Dự báo PM2.5 cho ngày kế tiếp sau ngày dữ liệu cuối trong CSDL (gee_overrides được giữ cho tương thích, không còn tác dụng)."""
    model, meta = load_model()
    r = du_bao_tu_chuoi(_doc_chuoi_pm25(), model, meta, 1)
    if isinstance(r, dict):
        return r
    kq, th = r
    x = kq[0]
    pv = th["pv"]
    return {"ngay_du_bao": x["ngay"], "pm25_du_bao": x["pm25"],
            "khoang_dao_dong": round((pv["q90"] - pv["q10"]) / 2, 2) if pv else None,
            "khoang_80": x.get("khoang_80"), "muc_do": x["muc_do"], "model_r2": th["model_r2"],
            "ky_nang_so_voi_hom_qua": th["ky_nang"], "co_ky_nang_y_nghia": th["co_y_nghia"],
            "pm25_neo_hom_nay": th["pm25_hom_nay_nen"], "ngay_du_lieu_cuoi": th["ngay_du_lieu_cuoi"],
            "ngay_he_thong": th["ngay_he_thong"], "so_ngay_bu": th["so_ngay_bu"], "xac_suat_vuot": x.get("xac_suat_vuot"), "ghi_chu": GHI_CHU}


def predict_multiple_days(so_ngay=7):
    """Dự báo đệ quy nhiều ngày. CHỈ ngày đầu được kiểm chứng (da_kiem_chung=True); các ngày sau chỉ mang tính tham khảo."""
    model, meta = load_model()
    r = du_bao_tu_chuoi(_doc_chuoi_pm25(), model, meta, so_ngay)
    if isinstance(r, dict):
        return r
    return r[0]


def du_bao_theo_thang_tu_chuoi(df, so_thang=3, hom_nay=None):
    """Xu hướng PM2.5 các tháng tới (hàm thuần). df: ngay_do, pm25_mean theo ngày (càng dài càng tốt, ≥ 1 năm).
    Phương pháp khí hậu học có hiệu chỉnh dị thường: dự báo tháng m (cách hiện tại k tháng) =
    trung bình cùng tháng các năm trước + dị thường 30 ngày gần nhất × 0,5^k (dị thường tắt dần).
    Khoảng = thấp nhất–cao nhất của cùng tháng các năm trước (dịch theo dị thường). Kiểm chứng ngược (backtest) mỗi tháng lịch sử:
    khí hậu học bỏ chính năm đó so với cách đoán đơn giản "tháng sau = tháng trước". ĐÂY LÀ XU HƯỚNG THEO MÙA, KHÔNG phải dự báo
    thời tiết hằng ngày: tháng mùa khô (12–4) thường bụi cao hơn mùa mưa (5–11) ở TP.HCM."""
    hom_nay = pd.Timestamp(hom_nay or date.today()).normalize()
    d = df.dropna(subset=["pm25_mean"]).copy()
    d["ngay_do"] = pd.to_datetime(d["ngay_do"])
    d = d[d["ngay_do"] <= hom_nay]
    d["thang"] = d["ngay_do"].dt.to_period("M")
    dem = d.groupby("thang")["pm25_mean"].agg(["mean", "count"])
    du = dem[(dem["count"] >= 20) & (dem.index < hom_nay.to_period("M"))]          # tháng đủ số liệu, đã kết thúc
    if du.empty or du.index.month.nunique() < 12:
        return {"error": "Chưa đủ 12 tháng số liệu trọn vẹn để tính xu hướng theo mùa."}
    bang = pd.DataFrame({"nam": du.index.year, "thang": du.index.month, "pm25": du["mean"].values})
    kh = bang.groupby("thang")["pm25"].agg(["mean", "min", "max", "count"])
    gan = d[d["ngay_do"] > hom_nay - pd.Timedelta(days=30)]
    di_thuong = float((gan["pm25_mean"] - gan["ngay_do"].dt.month.map(kh["mean"])).mean()) if len(gan) >= 10 else 0.0

    kq = []
    for k in range(1, int(so_thang) + 1):
        t = (hom_nay.to_period("M") + k)
        c = kh.loc[t.month]
        dt = di_thuong * 0.5 ** k
        p = float(c["mean"] + dt)
        kq.append({"thang": str(t), "pm25": round(p, 1), "thap": round(max(float(c["min"]) + dt, 0), 1), "cao": round(float(c["max"]) + dt, 1),
                   "muc_do": _phan_loai(p), "so_nam_lich_su": int(c["count"]), "mua": "khô" if t.month in (12, 1, 2, 3, 4) else "mưa"})

    # Kiểm chứng ngược: dự báo tháng sau từ tháng trước, khí hậu học bỏ năm đang thử
    sai_kh, sai_gn = [], []
    du_list = list(du.index)
    for i in range(1, len(du_list)):
        t, tr = du_list[i], du_list[i - 1]
        if (t - tr).n != 1:
            continue
        khac = bang[(bang["thang"] == t.month) & (bang["nam"] != t.year)]["pm25"]
        khac_tr = bang[(bang["thang"] == tr.month) & (bang["nam"] != t.year)]["pm25"]
        if khac.empty or khac_tr.empty:
            continue
        du_doan = khac.mean() + (du.loc[tr, "mean"] - khac_tr.mean()) * 0.5
        sai_kh.append(abs(du_doan - du.loc[t, "mean"]))
        sai_gn.append(abs(du.loc[tr, "mean"] - du.loc[t, "mean"]))
    danh_gia = None
    if sai_kh:
        mae_kh, mae_gn = float(np.mean(sai_kh)), float(np.mean(sai_gn))
        danh_gia = {"so_thang_thu": len(sai_kh), "MAE_khi_hau_hoc": round(mae_kh, 2), "MAE_thang_sau_bang_thang_truoc": round(mae_gn, 2),
                    "ky_nang": round(1 - mae_kh / mae_gn, 3) if mae_gn else None}
    return {"ngay_he_thong": str(hom_nay.date()), "di_thuong_30_ngay": round(di_thuong, 2), "thang": kq,
            "khi_hau": [{"thang": int(m), "pm25_tb": round(float(r["mean"]), 1), "thap": round(float(r["min"]), 1), "cao": round(float(r["max"]), 1),
                          "so_nam": int(r["count"])} for m, r in kh.iterrows()],
            "danh_gia": danh_gia,
            "phuong_phap": "Khí hậu học theo tháng (trung bình cùng tháng các năm trước) + dị thường 30 ngày gần nhất tắt dần 0,5^k. "
                           "Đây là xu hướng theo mùa, không phải dự báo thời tiết; khoảng là thấp nhất–cao nhất cùng tháng các năm trước."}


def du_bao_theo_thang(so_thang=3):
    return du_bao_theo_thang_tu_chuoi(_doc_chuoi_pm25(so_ngay=2000), so_thang)


if __name__ == "__main__":
    for k, v in predict_next_day().items():
        print(f"{k}: {v}")
