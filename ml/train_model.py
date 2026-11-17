"""
Huấn luyện mô hình PM2.5 THEO NGÀY — bản đánh giá trung thực (v3.7).

Chạy từ THƯ MỤC GỐC dự án:   python ml/train_model.py            (đọc CSDL)
                              python ml/train_model.py --csv du_lieu/ngay.csv   (không cần CSDL, để thử)

Khác bản cũ:
  1. So với nền (baseline) "hôm nay = hôm qua" và "trung bình 7 ngày trước"; báo "kỹ năng" = 1 - RMSE_mô_hình / RMSE_nền.
  2. Chọn siêu tham số bằng RMSE (kiểm chéo theo thời gian) CHỈ trên tập huấn luyện; tập kiểm tra 15% cuối chỉ dùng 1 lần.
  3. Chỉ số lưu kèm mô hình là của mô hình đã được kiểm tra; mô hình lưu cuối (huấn luyện lại trên toàn bộ) ghi rõ điều này.
  4. Hai bộ đặc trưng, nói rõ ý nghĩa:
       - "ước lượng trong ngày": có NO2/CO/SO2/O3 + thời tiết CỦA CHÍNH NGÀY ĐÓ (không phải dự báo, vì các giá trị này chưa biết trước);
       - "dự báo ngày mai": chỉ dùng thông tin tới hôm qua + lịch.
     Mô hình lưu cho backend vẫn là bộ "ước lượng trong ngày" (giữ tương thích), nhưng báo cáo phải gọi đúng tên.
  5. Lưu thêm models/model_metadata.json (đọc được bằng mọi trình soạn thảo) kèm phiên bản scikit-learn.
  6. (v3.8) Lưu CẢ HAI mô hình; kiểm chéo cuốn chiếu (expanding window); kỹ năng theo mùa (mưa/khô); khoảng tin cậy
     bootstrap theo khối 7 ngày. Việc đối chiếu với trạm đo thật nằm ở data_pipeline/doi_chieu_tram_that.py.
MLflow là tùy chọn: có cài thì ghi log, không có thì bỏ qua.
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.tree import DecisionTreeRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit

GOC = Path(__file__).resolve().parent.parent
MODEL_DIR = GOC / "models"
TARGET = "pm25_mean"

FEATURES = [  # ƯỚC LƯỢNG TRONG NGÀY (dùng biến của chính ngày đó)
    "no2_mean", "co_gee", "so2_gee", "o3_mean",
    "nhiet_do_mean", "do_am_mean", "gio_toc_do_mean", "mua_tong",
    "thang", "ngay_trong_tuan", "la_cuoi_tuan",
    "pm25_lag1", "pm25_lag2", "pm25_lag3", "pm25_lag5", "pm25_lag7",
    "no2_lag1", "no2_lag2", "gio_lag1", "gio_lag2",
    "pm25_rolling3", "pm25_rolling7", "pm25_std7", "pm25_delta",
    "gio_rolling3", "nhietdo_x_doam",
]
FEATURES_DU_BAO = [  # chỉ PM2.5 quá khứ + lịch: không cần NO2 vệ tinh (trễ 2–3 tuần) hay thời tiết tương lai
    "thang", "ngay_trong_tuan", "la_cuoi_tuan",
    "pm25_lag1", "pm25_lag2", "pm25_lag3", "pm25_lag5", "pm25_lag7",
    "pm25_rolling3", "pm25_rolling7", "pm25_std7", "pm25_delta",
]
TI_LE_KIEM_TRA = 0.15


def doc_tu_csdl() -> pd.DataFrame:
    from dotenv import load_dotenv
    from sqlalchemy import create_engine
    from urllib.parse import quote_plus
    load_dotenv(GOC / ".env")
    g = os.getenv
    # Ưu tiên DATABASE_URL (giống docker-compose/backend); nếu không có thì ghép, mã hóa mật khẩu có ký tự đặc biệt
    url = g("DATABASE_URL") or (f"postgresql://{g('DB_USER')}:{quote_plus(g('DB_PASS') or '')}"
                                f"@{g('DB_HOST')}:{g('DB_PORT')}/{g('DB_NAME')}")
    engine = create_engine(url)
    gee = pd.read_sql("SELECT ngay_do, no2_mean, co_mean AS co_gee, so2_mean AS so2_gee FROM du_lieu_gee_tphcm", engine)
    tram = pd.read_sql("""SELECT ngay_do, pm25_mean, pm10_mean, o3_mean, nhiet_do_mean, do_am_mean,
                                 gio_toc_do_mean, mua_tong FROM du_lieu_tram_mat_dat""", engine)
    gee["ngay_do"] = pd.to_datetime(gee["ngay_do"])
    tram["ngay_do"] = pd.to_datetime(tram["ngay_do"])
    # Mỗi bảng có thể có NHIỀU dòng mỗi ngày (nhiều trạm/ô lưới). Phải gộp về MỘT dòng/ngày (trung bình toàn thành phố)
    # TRƯỚC khi nối và tạo lag; nếu không, "hôm qua" (shift 1) thực ra là dòng của trạm khác CÙNG NGÀY → rò rỉ, R² ảo.
    print(f"  Dòng thô: GEE {len(gee)}, trạm {len(tram)}  ·  ngày khác nhau: GEE {gee['ngay_do'].nunique()}, trạm {tram['ngay_do'].nunique()}")
    gee = gee.groupby("ngay_do", as_index=False).mean(numeric_only=True)
    tram = tram.groupby("ngay_do", as_index=False).mean(numeric_only=True)
    return pd.merge(tram, gee, on="ngay_do", how="left")  # giữ mọi ngày có PM2.5; NO2/CO/SO2 vệ tinh có thể thiếu


def tao_dac_trung(raw: pd.DataFrame) -> pd.DataFrame:
    """Mọi lag/rolling dùng shift(>=1) nên chỉ nhìn quá khứ. Chuỗi được đưa về LỊCH NGÀY ĐẦY ĐỦ (ngày thiếu = NaN)
    để lag1 luôn là đúng 'hôm qua' (không bị nhảy qua ngày thiếu). KHÔNG dropna ở đây: mỗi mô hình tự loại dòng thiếu."""
    df = raw.sort_values("ngay_do").set_index("ngay_do").asfreq("D")
    df["so2_gee"] = df["so2_gee"].clip(lower=0)
    df["thang"] = df.index.month
    df["ngay_trong_tuan"] = df.index.dayofweek
    df["la_cuoi_tuan"] = (df["ngay_trong_tuan"] >= 5).astype(int)
    for lag in [1, 2, 3, 5, 7]:
        df[f"pm25_lag{lag}"] = df[TARGET].shift(lag)
    for lag in [1, 2]:
        df[f"no2_lag{lag}"] = df["no2_mean"].shift(lag)
        df[f"gio_lag{lag}"] = df["gio_toc_do_mean"].shift(lag)
    df["pm25_rolling3"] = df[TARGET].shift(1).rolling(3).mean()
    df["pm25_rolling7"] = df[TARGET].shift(1).rolling(7).mean()
    df["pm25_std7"] = df[TARGET].shift(1).rolling(7).std()
    df["pm25_delta"] = df[TARGET].shift(1) - df[TARGET].shift(2)
    df["gio_rolling3"] = df["gio_toc_do_mean"].shift(1).rolling(3).mean()
    df["nhietdo_x_doam"] = df["nhiet_do_mean"] * df["do_am_mean"]
    return df.rename_axis("ngay_do").reset_index()


def _rmse(a, b):
    return float(mean_squared_error(a, b) ** 0.5)


def _so(y, pred):
    return {"RMSE": _rmse(y, pred), "MAE": float(mean_absolute_error(y, pred)), "R2": float(r2_score(y, pred))}


def _rf_tinh_chinh(X, y, nhanh=False):
    luoi = {"n_estimators": [100] if nhanh else [100, 200], "max_depth": [8] if nhanh else [8, 12, None],
            "min_samples_leaf": [2, 5]}
    gs = GridSearchCV(RandomForestRegressor(random_state=42, n_jobs=-1), luoi,
                      cv=TimeSeriesSplit(n_splits=4), scoring="neg_root_mean_squared_error", n_jobs=1)
    gs.fit(X, y)
    return gs


def _dt_tinh_chinh(X, y, nhanh=False):
    """Cay quyet dinh co tinh chinh do sau / la toi thieu bang kiem cheo theo thoi gian tren TAP HUAN LUYEN,
    de so sanh cong bang voi RF va tranh cay mac dinh qua khop (overfit)."""
    luoi = {"max_depth": [5, 8] if nhanh else [4, 6, 8, 12, None],
            "min_samples_leaf": [5] if nhanh else [2, 5, 10, 20]}
    gs = GridSearchCV(DecisionTreeRegressor(random_state=42), luoi,
                      cv=TimeSeriesSplit(n_splits=4), scoring="neg_root_mean_squared_error", n_jobs=1)
    gs.fit(X, y)
    return gs


MUA_MUA = {5, 6, 7, 8, 9, 10}  # TP.HCM: mùa mưa tháng 5–10, mùa khô tháng 11–4


def _bootstrap_ky_nang(y, pred_mh, pred_nen, khoi=7, lan=1000, seed=42):
    """Khoảng tin cậy 95% của kỹ năng = 1 - RMSE_mh/RMSE_nền, lấy mẫu lại theo khối ngày liên tiếp (giữ tự tương quan)."""
    y, a, b = np.asarray(y, float), np.asarray(pred_mh, float), np.asarray(pred_nen, float)
    n = len(y)
    if n < 2 * khoi:
        return None
    em, en = (y - a) ** 2, (y - b) ** 2
    r = np.random.default_rng(seed)
    so_khoi = int(np.ceil(n / khoi))
    ks = []
    for _ in range(lan):
        st = r.integers(0, n - khoi + 1, so_khoi)
        idx = np.concatenate([np.arange(i, i + khoi) for i in st])[:n]
        ks.append(1 - np.sqrt(em[idx].mean()) / np.sqrt(en[idx].mean()))
    return {"thap": float(np.percentile(ks, 2.5)), "cao": float(np.percentile(ks, 97.5))}


def kiem_cheo_cuon_chieu(df, cot, tham_so=None, so_lan=5, ti_le_dau=0.5, nhanh=False):
    """Expanding-window: huấn luyện trên [0, k), kiểm tra trên khối kế tiếp. Trả về kỹ năng từng lần,
    kỹ năng gộp, kỹ năng theo mùa và CI bootstrap của kỹ năng gộp (so với nền hôm qua)."""
    n = len(df)
    dau = int(n * ti_le_dau)
    # Siêu tham số CHỈ được chọn trên khối đầu [0, dau): các khối kiểm tra của cuốn chiếu nằm sau đó nên không bị rò rỉ lựa chọn.
    tham_so = _rf_tinh_chinh(df.iloc[:dau][cot], df.iloc[:dau][TARGET], nhanh).best_params_
    moc = np.linspace(dau, n, so_lan + 1).astype(int)
    ys, pm, pn, thang, tung = [], [], [], [], []
    for k in range(so_lan):
        tr, te = df.iloc[:moc[k]], df.iloc[moc[k]:moc[k + 1]]
        m = RandomForestRegressor(**tham_so, random_state=42, n_jobs=-1).fit(tr[cot], tr[TARGET])
        p = m.predict(te[cot])
        ys += list(te[TARGET]); pm += list(p); pn += list(te["pm25_lag1"]); thang += list(te["thang"])
        tung.append({"tu": str(te["ngay_do"].iloc[0].date()), "den": str(te["ngay_do"].iloc[-1].date()), "so_ngay": len(te),
                     "ky_nang": float(1 - _rmse(te[TARGET], p) / _rmse(te[TARGET], te["pm25_lag1"]))})
    ys, pm, pn, thang = map(np.asarray, (ys, pm, pn, thang))
    mua = np.isin(thang, list(MUA_MUA))
    theo_mua = {}
    for ten, mask in (("mua_mua", mua), ("mua_kho", ~mua)):
        if mask.sum() >= 14:
            theo_mua[ten] = {"so_ngay": int(mask.sum()), "ky_nang": float(1 - _rmse(ys[mask], pm[mask]) / _rmse(ys[mask], pn[mask]))}
        else:
            theo_mua[ten] = {"so_ngay": int(mask.sum()), "ky_nang": None}
    return {"tung_lan": tung, "gop": {"so_ngay": len(ys), "ky_nang": float(1 - _rmse(ys, pm) / _rmse(ys, pn)),
            "ci95": _bootstrap_ky_nang(ys, pm, pn)}, "theo_mua": theo_mua}


def danh_gia(df: pd.DataFrame, nhanh=False):
    """Trả về (kết quả, {tên: mô hình huấn luyện trên toàn bộ}). Không đụng tới đĩa/CSDL.
    Mỗi mô hình tự loại các dòng thiếu của riêng nó, nên mô hình dự báo (chỉ cần PM2.5) có nhiều ngày hơn mô hình ước lượng."""
    kq = {"so_dong_lich": len(df), "mo_hinh": {}}
    cac_mo_hinh = {}
    for ten, cot in (("uoc_luong_trong_ngay", FEATURES), ("du_bao_ngay_mai", FEATURES_DU_BAO)):
        d = df.dropna(subset=cot + [TARGET]).reset_index(drop=True)
        n = len(d)
        cat = int(n * (1 - TI_LE_KIEM_TRA))
        tr, te = d.iloc[:cat], d.iloc[cat:]
        y_tr, y_te = tr[TARGET], te[TARGET]
        nen = {"hom_nay_bang_hom_qua": _so(y_te, te["pm25_lag1"]), "tb_7_ngay_truoc": _so(y_te, te["pm25_rolling7"])}
        rmse_nen = nen["hom_nay_bang_hom_qua"]["RMSE"]

        lr = LinearRegression().fit(tr[cot], y_tr)
        gs = _rf_tinh_chinh(tr[cot], y_tr, nhanh)
        rf = gs.best_estimator_
        p_rf = rf.predict(te[cot])
        gs_dt = _dt_tinh_chinh(tr[cot], y_tr, nhanh)
        dt = gs_dt.best_estimator_
        m_rf, m_lr = _so(y_te, p_rf), _so(y_te, lr.predict(te[cot]))
        m_dt = _so(y_te, dt.predict(te[cot]))
        m_dt["tham_so"] = gs_dt.best_params_
        for m in (m_rf, m_lr, m_dt):
            m["ky_nang_so_voi_hom_qua"] = 1 - m["RMSE"] / rmse_nen
        m_rf["CV_RMSE_tren_tap_huan_luyen"] = float(-gs.best_score_)
        m_rf["tham_so"] = gs.best_params_
        m_rf["ky_nang_ci95_bootstrap"] = _bootstrap_ky_nang(y_te, p_rf, te["pm25_lag1"])
        sai = np.asarray(y_te) - p_rf          # phân vị sai số thực → khoảng dự báo thật (thay cho độ lệch chuẩn giữa các cây)
        m_rf["phan_vi_sai_so"] = {"q10": float(np.percentile(sai, 10)), "q90": float(np.percentile(sai, 90))}
        cv = kiem_cheo_cuon_chieu(d, cot, None, 3 if nhanh else 5, nhanh=nhanh)
        kq["mo_hinh"][ten] = {"so_mau": n, "so_mau_huan_luyen": len(tr), "so_mau_kiem_tra": len(te),
                              "kiem_tra_tu": str(te["ngay_do"].iloc[0].date()), "nen": nen,
                              "random_forest": m_rf, "hoi_quy_tuyen_tinh": m_lr, "cay_quyet_dinh": m_dt, "so_dac_trung": len(cot),
                              "kiem_cheo_cuon_chieu": cv}
        cac_mo_hinh[ten] = RandomForestRegressor(**gs.best_params_, random_state=42, n_jobs=-1).fit(d[cot], d[TARGET])
        if ten == "uoc_luong_trong_ngay":
            # Dùng cho trang KỊCH BẢN: hồi quy tuyến tính (đường nhạy đơn điệu, dễ giải thích) + khoảng giá trị đã gặp khi huấn luyện
            cac_mo_hinh["uoc_luong_tuyen_tinh"] = LinearRegression().fit(d[cot], d[TARGET])
            kq["khoang_dac_trung"] = {c: {"min": float(d[c].min()), "p01": float(d[c].quantile(0.01)),
                                          "p99": float(d[c].quantile(0.99)), "max": float(d[c].max())} for c in cot}
    kq["luu_y"] = [
        "Chỉ số của mỗi mô hình là của bản huấn luyện trên phần đầu và kiểm tra trên 15% cuối theo thời gian; "
        "mô hình lưu cho backend được huấn luyện lại trên toàn bộ nên chưa có tập kiểm tra riêng.",
        "'Ước lượng trong ngày' dùng NO2/CO/SO2/O3 và thời tiết của chính ngày đó, nên KHÔNG phải dự báo trước. "
        "Chỉ 'dự báo ngày mai' (chỉ dùng PM2.5 đến hôm qua + lịch) mới là dự báo thật.",
        "Kỹ năng > 0: tốt hơn nền 'hôm nay = hôm qua'; <= 0: không hơn được nền, không được khẳng định mô hình có giá trị dự báo. "
        "Nếu khoảng tin cậy 95% chứa 0 thì chưa chứng minh được là hơn nền.",
        "Nhãn PM2.5 là số liệu mô hình CAMS (không phải đo mặt đất). Kỹ năng ở đây là so với CAMS, không phải so với không khí thật; "
        "xem models/doi_chieu_tram_that.json (do data_pipeline/doi_chieu_tram_that.py tạo) để biết CAMS lệch bao nhiêu so với số đo thật.",
        "Kiểm chéo cuốn chiếu: siêu tham số chỉ chọn trên 50% đầu của chuỗi; các khối kiểm tra nằm sau đó.",
    ]
    return kq, cac_mo_hinh


def in_ket_qua(kq):
    for ten, g in kq["mo_hinh"].items():
        print(f"\n[{ten}] {g['so_dac_trung']} đặc trưng · {g['so_mau']} ngày dùng được · kiểm tra {g['so_mau_kiem_tra']} ngày từ {g['kiem_tra_tu']}")
        for t, m in g["nen"].items():
            print(f"  Nền {t:<22} RMSE {m['RMSE']:.2f}  R² {m['R2']:.3f}")
        for loai in ("hoi_quy_tuyen_tinh", "cay_quyet_dinh", "random_forest"):
            m = g[loai]
            print(f"  {loai:<20} RMSE {m['RMSE']:.2f}  MAE {m['MAE']:.2f}  R² {m['R2']:.3f}  kỹ năng so với hôm qua {m['ky_nang_so_voi_hom_qua']:+.3f}")
        print(f"  Tham số RF: {g['random_forest']['tham_so']}")
        ci = g["random_forest"].get("ky_nang_ci95_bootstrap")
        if ci:
            print(f"  Kỹ năng RF (tập kiểm tra) 95% CI bootstrap: [{ci['thap']:+.3f}, {ci['cao']:+.3f}]")
        cv = g["kiem_cheo_cuon_chieu"]
        print("  Kiểm chéo cuốn chiếu (kỹ năng từng lần): " + ", ".join(f"{c['ky_nang']:+.3f}" for c in cv["tung_lan"]))
        gp = cv["gop"]; ci2 = gp["ci95"]
        print(f"  Gộp {gp['so_ngay']} ngày: kỹ năng {gp['ky_nang']:+.3f}" + (f"  CI95 [{ci2['thap']:+.3f}, {ci2['cao']:+.3f}]" if ci2 else ""))
        for mu, v in cv["theo_mua"].items():
            print(f"    {mu}: {v['so_ngay']} ngày, kỹ năng " + ("không đủ mẫu" if v["ky_nang"] is None else f"{v['ky_nang']:+.3f}"))
    print("\nLưu ý: " + "\n       ".join(kq["luu_y"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="CSV có các cột ngay_do, no2_mean, co_gee, so2_gee, pm25_mean, o3_mean, nhiet_do_mean, do_am_mean, gio_toc_do_mean, mua_tong")
    ap.add_argument("--nhanh", action="store_true", help="lưới tham số nhỏ để chạy thử")
    a = ap.parse_args()
    raw = pd.read_csv(a.csv, parse_dates=["ngay_do"]) if a.csv else doc_tu_csdl()
    raw = raw.groupby("ngay_do", as_index=False).mean(numeric_only=True)  # đảm bảo 1 dòng/ngày (cả khi dùng --csv)
    df = tao_dac_trung(raw)
    assert df["ngay_do"].is_unique, "Còn ngày trùng lặp: chuỗi thời gian sai"
    print(f"[1] {len(df)} ngày trên lịch, {df['ngay_do'].min().date()} → {df['ngay_do'].max().date()}  ·  ngày có PM2.5: {int(df[TARGET].notna().sum())}")
    kq, mos = danh_gia(df, a.nhanh)
    in_ket_qua(kq)

    MODEL_DIR.mkdir(exist_ok=True)
    ud = kq["mo_hinh"]["uoc_luong_trong_ngay"]; db = kq["mo_hinh"]["du_bao_ngay_mai"]
    meta = {"features": FEATURES, "features_du_bao_ngay_mai": FEATURES_DU_BAO, "khoang_dac_trung": kq["khoang_dac_trung"], "file_du_bao_ngay_mai": "random_forest_pm25_du_bao.pkl", "target": TARGET,
            "trained_at": datetime.now().isoformat(timespec="seconds"), "sklearn_version": sklearn.__version__,
            "data_range": f"{df['ngay_do'].min().date()} - {df['ngay_do'].max().date()}", "pm25_cuoi_cung_trong_du_lieu_huan_luyen": str(df.loc[df[TARGET].notna(), "ngay_do"].max().date()), "n_samples": ud["so_mau"], "n_samples_du_bao": db["so_mau"],
            "danh_gia": kq,
            # khóa cũ để backend không vỡ
            "random_forest_metrics": ud["random_forest"], "du_bao_metrics": db["random_forest"],
            "best_params": ud["random_forest"]["tham_so"]}
    joblib.dump(mos["uoc_luong_trong_ngay"], MODEL_DIR / "random_forest_pm25.pkl")
    joblib.dump(mos["du_bao_ngay_mai"], MODEL_DIR / "random_forest_pm25_du_bao.pkl")
    joblib.dump(mos["uoc_luong_tuyen_tinh"], MODEL_DIR / "linear_pm25.pkl")
    joblib.dump(meta, MODEL_DIR / "model_metadata.pkl")
    (MODEL_DIR / "model_metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\nĐã lưu models/random_forest_pm25.pkl (ước lượng trong ngày), random_forest_pm25_du_bao.pkl (DỰ BÁO ngày mai), model_metadata.pkl, model_metadata.json (scikit-learn {sklearn.__version__})")

    try:
        import mlflow
        import mlflow.sklearn
        mlflow.set_experiment("Air_Quality_PM25_Prediction")
        with mlflow.start_run(run_name="RF_ngay_v3_7"):
            g = kq["mo_hinh"]["uoc_luong_trong_ngay"]["random_forest"]
            mlflow.log_params(g["tham_so"])
            for k in ("RMSE", "MAE", "R2", "ky_nang_so_voi_hom_qua"):
                mlflow.log_metric("Test_" + k, g[k])
            mlflow.log_metric("Test_ky_nang_du_bao_ngay_mai", kq["mo_hinh"]["du_bao_ngay_mai"]["random_forest"]["ky_nang_so_voi_hom_qua"])
            tin = ["sklearn.tree._tree.Tree"]  # mô hình do chính ta vừa huấn luyện nên tin cậy
            mlflow.sklearn.log_model(mos["uoc_luong_trong_ngay"], name="random_forest_pm25", skops_trusted_types=tin)
            mlflow.sklearn.log_model(mos["du_bao_ngay_mai"], name="random_forest_pm25_du_bao", skops_trusted_types=tin)
        print("Đã ghi log MLflow.")
    except ImportError:
        print("(Không cài mlflow: bỏ qua ghi log MLflow.)")
    except Exception as exc:  # MLflow lỗi không được làm hỏng việc huấn luyện (file mô hình đã lưu ở trên)
        print(f"(MLflow lỗi, bỏ qua: {type(exc).__name__}: {str(exc)[:200]}. Mô hình vẫn đã được lưu.)")


if __name__ == "__main__":
    main()
