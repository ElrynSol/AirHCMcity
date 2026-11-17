"""Dự báo PM2.5 THEO NGÀY (v3.7) — dùng mô hình "dự báo ngày mai" (chỉ PM2.5 quá khứ + lịch).

Khác bản cũ:
  * Không còn dùng NO2/O3/thời tiết của hôm nay làm đặc trưng của ngày mai (đó là "ước lượng trong ngày", không phải dự báo).
  * Đặc trưng được tạo bằng ĐÚNG hàm tao_dac_trung của train_model.py (không lệch giữa huấn luyện và vận hành).
  * Nếu dữ liệu CSDL cũ quá 1 ngày thì TRẢ LỖI thay vì dự báo bằng số liệu cũ gán nhãn "ngày mai".
  * Khoảng dự báo là phân vị 10–90% của sai số thực trên tập kiểm tra (không phải độ lệch chuẩn giữa các cây).
  * Kỹ năng so với "mai = hôm nay" được trả kèm; nếu khoảng tin cậy chứa 0 thì cờ co_ky_nang_y_nghia = False.
Giữ các khóa cũ (ngay_du_bao, pm25_du_bao, khoang_dao_dong, muc_do, model_r2) để router/giao diện cũ không vỡ.
"""

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
    if pm25 <= 25: return "Tốt"
    if pm25 <= 50: return "Trung bình"
    if pm25 <= 100: return "Kém"
    return "Xấu"


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


def du_bao_tu_chuoi(df, model, meta, so_ngay=1, hom_nay=None):
    """Hàm thuần (không đọc CSDL) để dễ kiểm thử. df: cột ngay_do, pm25_mean (nhiều ngày gần nhất)."""
    hom_nay = pd.Timestamp(hom_nay or date.today())
    d = df.dropna(subset=["pm25_mean"]).sort_values("ngay_do").reset_index(drop=True)
    if len(d) < 8:
        return {"error": "Không đủ dữ liệu PM2.5 gần đây để dự báo (cần ít nhất 8 ngày)."}
    ngay_cuoi = d["ngay_do"].iloc[-1]
    tre = (hom_nay - ngay_cuoi).days
    if tre > 1:
        return {"error": f"Dữ liệu PM2.5 trong CSDL mới đến {ngay_cuoi.date()} (cũ {tre} ngày), không thể dự báo ngày kế tiếp một cách hợp lệ. "
                         "Hãy cập nhật CSDL (dong_bo_hang_ngay.py / download_openmeteo_data.py) hoặc dùng dự báo theo giờ (/api/v1/du-bao-gio)."}
    cot = meta["features_du_bao_ngay_mai"]
    chuoi = d[["ngay_do", "pm25_mean"]].copy()
    dm = meta.get("du_bao_metrics", {})
    pv = dm.get("phan_vi_sai_so")
    cv_ci = (meta.get("danh_gia", {}).get("mo_hinh", {}).get("du_bao_ngay_mai", {})
             .get("kiem_cheo_cuon_chieu", {}).get("gop", {}).get("ci95"))
    co_y_nghia = bool(cv_ci and cv_ci["thap"] > 0)
    kq = []
    for i in range(int(so_ngay)):
        ngay = chuoi["ngay_do"].iloc[-1] + timedelta(days=1)
        thu = pd.concat([chuoi, pd.DataFrame({"ngay_do": [ngay], "pm25_mean": [np.nan]})], ignore_index=True)
        f = tm.tao_dac_trung(_them_cot_thieu(thu)).iloc[-1]
        X = pd.DataFrame([f[cot].astype(float)])
        if X.isna().any().any():
            return {"error": "Thiếu số liệu PM2.5 trong 7 ngày gần nhất (có ngày trống) nên không tạo được đặc trưng."}
        p = float(model.predict(X)[0])
        muc = {"ngay": str(ngay.date()), "pm25": round(p, 2), "muc_do": _phan_loai(p), "bac_du_bao": i + 1,
               "da_kiem_chung": i == 0}   # chỉ bước 1 ngày được đánh giá; các bước sau là suy ra đệ quy, chưa kiểm chứng
        if pv:
            muc["khoang_80"] = {"thap": round(max(p + pv["q10"], 0), 2), "cao": round(p + pv["q90"], 2)}
        kq.append(muc)
        chuoi = pd.concat([chuoi, pd.DataFrame({"ngay_do": [ngay], "pm25_mean": [p]})], ignore_index=True)
    return kq, {"ngay_du_lieu_cuoi": str(ngay_cuoi.date()), "pm25_hom_nay_nen": float(d["pm25_mean"].iloc[-1]),
                "model_r2": dm.get("R2"), "ky_nang": dm.get("ky_nang_so_voi_hom_qua"), "co_y_nghia": co_y_nghia, "pv": pv}


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
            "pm25_neo_hom_nay": th["pm25_hom_nay_nen"], "ngay_du_lieu_cuoi": th["ngay_du_lieu_cuoi"], "ghi_chu": GHI_CHU}


def predict_multiple_days(so_ngay=7):
    """Dự báo đệ quy nhiều ngày. CHỈ ngày đầu được kiểm chứng (da_kiem_chung=True); các ngày sau chỉ mang tính tham khảo."""
    model, meta = load_model()
    r = du_bao_tu_chuoi(_doc_chuoi_pm25(), model, meta, so_ngay)
    if isinstance(r, dict):
        return r
    return r[0]


if __name__ == "__main__":
    for k, v in predict_next_day().items():
        print(f"{k}: {v}")
