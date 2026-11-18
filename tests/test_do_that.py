"""Kiểm thử mô hình dự báo từ số đo thật (ml/mo_hinh_tram_that.py), dự báo nhiều chất (ml/du_bao_da_chat.py) và QA/QC OpenAQ."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

GOC = Path(__file__).resolve().parent.parent
for p in (GOC / "ml", GOC / "data_pipeline"):
    sys.path.insert(0, str(p))

import mo_hinh_tram_that as mt  # noqa: E402
import du_bao_da_chat as ddc  # noqa: E402
from tai_tram_that import kiem_soat_chat_luong  # noqa: E402


def _gia_lap(n=300, seed=0):
    rng = np.random.default_rng(seed)
    ngay = pd.date_range("2025-01-01", periods=n, freq="D")
    y = np.empty(n); y[0] = 30
    for i in range(1, n):
        y[i] = 0.7 * y[i - 1] + 9 + rng.normal(0, 4)            # chuỗi tự hồi quy: "mai = hôm nay" khá tốt
    do = pd.DataFrame({"ngay": ngay, "y": y})
    ngoai = pd.DataFrame({"ngay": ngay, "cams": y * 0.5 + 10 + rng.normal(0, 8, n), "nhiet_do": 28.0, "do_am": 75.0, "gio": 8.0, "mua": 0.0})
    return do, ngoai


def test_qa_qc_loai_ma_loi_985_giu_gia_tri_cao_hop_ly():
    d = pd.DataFrame({"pm25": [12.0, 985.0, 150.0, -3.0, 40.0]})
    sach, qc = kiem_soat_chat_luong(d)
    assert list(sach["pm25"]) == [12.0, 150.0, 40.0] and qc["loai"] == 2


def test_bang_dac_trung_khong_nhin_truoc_nhan():
    do, ngoai = _gia_lap(40)
    b = mt.tao_bang(do, ngoai)
    r = b.iloc[10]
    assert r["nhan"] == do.set_index("ngay").loc[r["ngay_du_bao"], "y"]        # nhãn là ngày mai
    assert r["y"] == do.set_index("ngay").loc[r["ngay"], "y"]                   # đặc trưng là hôm nay
    assert r["cams_mai"] == ngoai.set_index("ngay").loc[r["ngay_du_bao"], "cams"]


def test_danh_gia_so_sanh_voi_persistence_va_cams():
    do, ngoai = _gia_lap(300)
    kq, rf, bu = mt.danh_gia(mt.tao_bang(do, ngoai))
    m = kq["mo_hinh"]
    assert m["Mai = hôm nay (đo thật)"]["ky_nang"] == 0.0
    assert m["CAMS thô"]["ky_nang"] < 0                                         # CAMS nhiễu, lệch → kém persistence
    ci = m["Random Forest"]["ky_nang_ci95"]; assert ci["thap"] <= m["Random Forest"]["ky_nang"] <= ci["cao"]
    assert set(m["Random Forest"]["vuot_nguong"]) == {"QCVN_45", "Kem_50"}


def test_vuot_nguong_do_nhay_do_chinh_xac():
    y, p = np.array([10, 50, 60, 20, 47.0]), np.array([12, 55, 30, 50, 46.0])
    v = mt._vuot(y, p, 45)
    assert (v["bat_dung"], v["bo_sot"], v["bao_nham"]) == (2, 1, 1) and v["do_nhay"] == round(2 / 3, 3)


def test_du_bao_da_chat_chon_persistence_khi_khong_co_y_nghia():
    rng = np.random.default_rng(1)
    s = pd.Series(30 + np.cumsum(rng.normal(0, 3, 400)), index=pd.date_range("2024-01-01", periods=400, freq="D"))  # bước ngẫu nhiên
    dg, _ = ddc.danh_gia_chat(s)
    assert dg["mo_hinh"]["Mai = hôm nay"]["ky_nang"] == 0.0
    assert dg["mo_hinh_chon"] in ("Mai = hôm nay", "Hồi quy tuyến tính", "Random Forest")
    if dg["mo_hinh_chon"] != "Mai = hôm nay":
        assert dg["mo_hinh"][dg["mo_hinh_chon"]]["ky_nang_ci95"]["thap"] > 0
