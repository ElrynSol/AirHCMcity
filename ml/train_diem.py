"""Huấn luyện mô hình dự báo PM2.5 THEO TỪNG ĐIỂM (trạm) — bước "dự báo theo thời gian cho từng điểm ảnh" (v3.9).

Chạy từ THƯ MỤC GỐC dự án:   python ml/train_diem.py            (đọc CSDL)
Một mô hình Random Forest dùng chung cho mọi trạm (gộp các trạm), đặc trưng = PM2.5 quá khứ CỦA CHÍNH TRẠM đó + lịch.
Đánh giá chia theo thời gian (15% ngày cuối), so với nền "mai = hôm nay" của từng trạm, kỹ năng + CI bootstrap,
và đo riêng khả năng nắm bắt CHÊNH LỆCH GIỮA CÁC TRẠM (tương quan của độ lệch so với trung bình thành phố trong ngày).
Kết quả: models/random_forest_pm25_diem.pkl và models/diem_chi_so.json
"""

import json
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit

import train_model as tm

GOC = Path(__file__).resolve().parent.parent
MODEL_DIR = GOC / "models"
CAC_COT = ["no2_mean", "co_gee", "so2_gee", "o3_mean", "nhiet_do_mean", "do_am_mean", "gio_toc_do_mean", "mua_tong"]


def doc_tu_csdl() -> pd.DataFrame:
    import os
    from dotenv import load_dotenv
    from sqlalchemy import create_engine
    from urllib.parse import quote_plus
    load_dotenv(GOC / ".env")
    g = os.getenv
    url = g("DATABASE_URL") or (f"postgresql://{g('DB_USER')}:{quote_plus(g('DB_PASS') or '')}@{g('DB_HOST')}:{g('DB_PORT')}/{g('DB_NAME')}")
    df = pd.read_sql("SELECT tram_id, ngay_do, pm25_mean FROM du_lieu_tram_mat_dat", create_engine(url))
    df["ngay_do"] = pd.to_datetime(df["ngay_do"])
    return df


def tao_bang_dac_trung(dai: pd.DataFrame) -> pd.DataFrame:
    """dai: cột tram_id, ngay_do, pm25_mean (mỗi trạm một chuỗi). Đặc trưng tính RIÊNG từng trạm (lịch ngày đầy đủ)."""
    cac = []
    for tid, g in dai.groupby("tram_id"):
        g = g.sort_values("ngay_do").drop_duplicates("ngay_do")[["ngay_do", "pm25_mean"]].copy()
        for c in CAC_COT:
            g[c] = np.nan
        f = tm.tao_dac_trung(g)
        f["tram_id"] = tid
        cac.append(f)
    return pd.concat(cac, ignore_index=True)


def danh_gia_diem(dai: pd.DataFrame, nhanh=False):
    f = tao_bang_dac_trung(dai)
    cot = tm.FEATURES_DU_BAO
    d = f.dropna(subset=cot + [tm.TARGET]).sort_values(["ngay_do", "tram_id"]).reset_index(drop=True)
    ngay = np.sort(d["ngay_do"].unique())
    moc = ngay[int(len(ngay) * (1 - tm.TI_LE_KIEM_TRA))]
    tr, te = d[d["ngay_do"] < moc], d[d["ngay_do"] >= moc]
    luoi = {"n_estimators": [100] if nhanh else [150], "max_depth": [8] if nhanh else [8, 12], "min_samples_leaf": [5] if nhanh else [5, 20]}
    gs = GridSearchCV(RandomForestRegressor(random_state=42, n_jobs=-1), luoi, cv=TimeSeriesSplit(n_splits=3),
                      scoring="neg_root_mean_squared_error", n_jobs=1).fit(tr[cot], tr[tm.TARGET])
    rf = gs.best_estimator_
    p = rf.predict(te[cot])
    y, nen = te[tm.TARGET].to_numpy(), te["pm25_lag1"].to_numpy()
    n_tram = int(d["tram_id"].nunique())
    m = tm._so(y, p)
    m["ky_nang_so_voi_hom_qua"] = 1 - m["RMSE"] / tm._rmse(y, nen)
    m["RMSE_nen"] = tm._rmse(y, nen)
    m["ky_nang_ci95_bootstrap"] = tm._bootstrap_ky_nang(y, p, nen, khoi=7 * n_tram)
    sai = y - p
    m["phan_vi_sai_so"] = {"q10": float(np.percentile(sai, 10)), "q90": float(np.percentile(sai, 90))}
    # Chênh lệch KHÔNG GIAN: độ lệch của từng trạm so với trung bình thành phố trong cùng ngày
    t = te.assign(p=p)
    t["lech_that"] = t[tm.TARGET] - t.groupby("ngay_do")[tm.TARGET].transform("mean")
    t["lech_du_bao"] = t["p"] - t.groupby("ngay_do")["p"].transform("mean")
    kg = {"do_lech_chuan_that_giua_cac_tram": float(t["lech_that"].std()),
          "tuong_quan_lech_du_bao_va_that": float(t["lech_that"].corr(t["lech_du_bao"])) if t["lech_that"].std() > 0 else None,
          "chenh_max_min_trung_binh_moi_ngay": float(te.groupby("ngay_do")[tm.TARGET].agg(lambda s: s.max() - s.min()).mean())}
    kq = {"so_tram": n_tram, "so_mau": int(len(d)), "so_mau_kiem_tra": int(len(te)), "kiem_tra_tu": str(pd.Timestamp(moc).date()),
          "tham_so": gs.best_params_, "random_forest": m, "khong_gian": kg,
          "luu_y": ["Mô hình dùng chung cho mọi trạm, đặc trưng là PM2.5 quá khứ của chính trạm đó + lịch.",
                    "Nhãn PM2.5 từ số liệu mô hình CAMS (lưới ~0,4°): các trạm gần nhau có thể rơi vào cùng ô lưới nên chênh lệch giữa trạm có thể rất nhỏ.",
                    "Kỹ năng > 0 nhưng khoảng tin cậy chứa 0 thì chưa chứng minh được hơn nền 'mai = hôm nay'."],
          "trained_at": datetime.now().isoformat(timespec="seconds")}
    final = RandomForestRegressor(**gs.best_params_, random_state=42, n_jobs=-1).fit(d[cot], d[tm.TARGET])
    return kq, final


def main():
    dai = doc_tu_csdl()
    print(f"{len(dai)} dòng, {dai['tram_id'].nunique()} trạm, {dai['ngay_do'].min().date()} → {dai['ngay_do'].max().date()}")
    kq, model = danh_gia_diem(dai)
    m, kg = kq["random_forest"], kq["khong_gian"]
    ci = m["ky_nang_ci95_bootstrap"]
    print(f"\nKiểm tra {kq['so_mau_kiem_tra']} dòng từ {kq['kiem_tra_tu']}: RMSE {m['RMSE']:.2f} (nền {m['RMSE_nen']:.2f}), R² {m['R2']:.3f}, "
          f"kỹ năng {m['ky_nang_so_voi_hom_qua']:+.3f}" + (f" CI95 [{ci['thap']:+.3f}, {ci['cao']:+.3f}]" if ci else ""))
    print(f"Chênh lệch giữa các trạm: độ lệch chuẩn {kg['do_lech_chuan_that_giua_cac_tram']:.2f} µg/m³, chênh max-min trung bình {kg['chenh_max_min_trung_binh_moi_ngay']:.2f}; "
          f"tương quan độ lệch dự báo–thật: {kg['tuong_quan_lech_du_bao_va_that']}")
    MODEL_DIR.mkdir(exist_ok=True)
    joblib.dump(model, MODEL_DIR / "random_forest_pm25_diem.pkl")
    (MODEL_DIR / "diem_chi_so.json").write_text(json.dumps(kq, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("Đã lưu models/random_forest_pm25_diem.pkl và models/diem_chi_so.json")


if __name__ == "__main__":
    main()
