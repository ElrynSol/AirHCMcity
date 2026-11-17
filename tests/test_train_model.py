"""Thử quy trình đánh giá theo ngày trên dữ liệu giả (không cần CSDL)."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import train_model as tm


def _gia(n=500, seed=0):
    r = np.random.default_rng(seed)
    pm = 30 + np.cumsum(r.normal(0, 3, n)) * 0.3 + r.normal(0, 4, n)
    return pd.DataFrame({"ngay_do": pd.date_range("2023-01-01", periods=n), "pm25_mean": np.abs(pm) + 5,
        "no2_mean": r.normal(3e-5, 5e-6, n), "co_gee": r.normal(0.03, 0.005, n), "so2_gee": r.normal(1e-4, 3e-5, n),
        "o3_mean": r.normal(40, 8, n), "nhiet_do_mean": r.normal(29, 2, n), "do_am_mean": r.normal(75, 8, n),
        "gio_toc_do_mean": r.normal(8, 2, n), "mua_tong": np.abs(r.normal(2, 3, n))})


def test_dac_trung_khong_nhin_tuong_lai():
    raw = _gia(); a = tm.tao_dac_trung(raw)
    raw2 = raw.copy(); raw2.loc[raw2.index[-1], "pm25_mean"] = 9999
    b = tm.tao_dac_trung(raw2)
    # đổi giá trị ngày cuối không được làm đổi đặc trưng của các ngày trước nó
    assert np.allclose(a[tm.FEATURES_DU_BAO].iloc[:-1].values.astype(float), b[tm.FEATURES_DU_BAO].iloc[:-1].values.astype(float), equal_nan=True)


def test_danh_gia_co_nen_va_chia_theo_thoi_gian():
    df = tm.tao_dac_trung(_gia())
    kq, mos = tm.danh_gia(df, nhanh=True)
    assert set(mos) == {"uoc_luong_trong_ngay", "du_bao_ngay_mai", "uoc_luong_tuyen_tinh"}
    assert set(kq["khoang_dac_trung"]) == set(tm.FEATURES)
    assert mos["du_bao_ngay_mai"].n_features_in_ == len(tm.FEATURES_DU_BAO)
    gg = kq["mo_hinh"]["du_bao_ngay_mai"]
    assert gg["so_mau_huan_luyen"] + gg["so_mau_kiem_tra"] == gg["so_mau"]
    assert "hom_nay_bang_hom_qua" in gg["nen"]
    g = gg["random_forest"]
    assert "ky_nang_so_voi_hom_qua" in g and "RMSE" in g and g["phan_vi_sai_so"]["q10"] <= g["phan_vi_sai_so"]["q90"]


def test_cuon_chieu_va_theo_mua():
    df = tm.tao_dac_trung(_gia(700))
    kq, _ = tm.danh_gia(df, nhanh=True)
    cv = kq["mo_hinh"]["du_bao_ngay_mai"]["kiem_cheo_cuon_chieu"]
    assert len(cv["tung_lan"]) == 3
    assert cv["gop"]["ci95"]["thap"] <= cv["gop"]["ky_nang"] <= cv["gop"]["ci95"]["cao"]
    assert set(cv["theo_mua"]) == {"mua_mua", "mua_kho"}


def test_lich_ngay_day_du_lag1_la_dung_hom_qua():
    raw = _gia(40).drop(index=[10]).reset_index(drop=True)   # thiếu 1 ngày
    d = tm.tao_dac_trung(raw)
    hang = d[d["ngay_do"] == raw["ngay_do"].iloc[10]].iloc[0]   # ngày ngay sau chỗ thiếu
    assert np.isnan(hang["pm25_lag1"])                        # hôm qua không có số liệu → NaN, không nhảy lùi 2 ngày
