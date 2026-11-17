import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import train_model as tm
import predict as pr
from test_train_model import _gia


def _mo_hinh():
    df = tm.tao_dac_trung(_gia(400))
    kq, mos = tm.danh_gia(df, nhanh=True)
    meta = {"features_du_bao_ngay_mai": tm.FEATURES_DU_BAO, "du_bao_metrics": kq["mo_hinh"]["du_bao_ngay_mai"]["random_forest"],
            "danh_gia": kq}
    return mos["du_bao_ngay_mai"], meta


def test_du_bao_hop_le_va_khoang_80():
    model, meta = _mo_hinh()
    raw = _gia(60)[["ngay_do", "pm25_mean"]]
    hom_nay = raw["ngay_do"].iloc[-1]
    kq, th = pr.du_bao_tu_chuoi(raw, model, meta, 3, hom_nay)
    assert len(kq) == 3 and kq[0]["da_kiem_chung"] and not kq[1]["da_kiem_chung"]
    assert kq[0]["ngay"] == str((hom_nay + pd.Timedelta(days=1)).date())
    assert kq[0]["khoang_80"]["thap"] <= kq[0]["pm25"] <= kq[0]["khoang_80"]["cao"]


def test_du_lieu_cu_thi_bao_loi():
    model, meta = _mo_hinh()
    raw = _gia(60)[["ngay_do", "pm25_mean"]]
    r = pr.du_bao_tu_chuoi(raw, model, meta, 1, raw["ngay_do"].iloc[-1] + pd.Timedelta(days=12))
    assert isinstance(r, dict) and "cũ 12 ngày" in r["error"]


def test_thieu_ngay_gan_day_thi_bao_loi():
    model, meta = _mo_hinh()
    raw = _gia(60)[["ngay_do", "pm25_mean"]].drop(index=[55]).reset_index(drop=True)
    r = pr.du_bao_tu_chuoi(raw, model, meta, 1, raw["ngay_do"].iloc[-1])
    assert isinstance(r, dict) and "error" in r
