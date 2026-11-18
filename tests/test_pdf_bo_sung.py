"""Kiểm thử các phần bổ sung theo đề cương "Hệ thống dự báo, phân tích xác suất và truy tìm nguồn thải":
ngưỡng QCVN 05:2023 theo ngày, công thức gió/hoa gió, dự báo theo ngày hệ thống, xác suất vượt ngưỡng, xu hướng theo tháng."""
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

GOC = Path(__file__).resolve().parent.parent
for p in (GOC / "backend", GOC / "ml", GOC / "tests"):
    sys.path.insert(0, str(p))

from core.nguong import qcvn_pm25_24h, bang_nguong  # noqa: E402
from services.hoa_gio import ws_wd, chi_so_huong, tinh_hoa_gio  # noqa: E402
import predict as pr  # noqa: E402


def test_nguong_qcvn_pm25_doi_tu_2026():
    assert qcvn_pm25_24h(date(2025, 12, 31)) == 50.0
    assert qcvn_pm25_24h("2026-01-01") == 45.0
    b = bang_nguong(date(2026, 11, 18))
    assert b["qcvn_05_2023"]["pm25_24h"] == 45.0 and b["who_2021"]["pm25_24h"] == 15.0


def test_cong_thuc_gio_dung_vi_du_de_cuong():
    ws, wd = ws_wd(-2, -1)                     # U = −2, V = −1 → 2,236 m/s, 63,4° (gió Đông Bắc)
    assert abs(float(ws) - 2.236) < 1e-3 and abs(float(wd) - 63.43) < 0.05
    _, wd_bac = ws_wd(0, -3)                   # V âm: không khí đi về Nam → gió THỔI TỪ Bắc
    assert abs(float(wd_bac) % 360) < 1e-9
    assert list(chi_so_huong([0, 22, 23, 350, 180, 67.4], 8)) == [0, 0, 1, 0, 4, 1]


def test_hoa_gio_tach_tan_suat_va_xac_suat_vuot():
    # 60 giờ gió Đông sạch, 10 giờ gió Tây bẩn, 5 giờ lặng gió
    df = pd.DataFrame({"ws": [3.0] * 60 + [2.5] * 10 + [0.2] * 5, "wd": [90.0] * 60 + [270.0] * 10 + [0.0] * 5,
                       "pm25": [10.0] * 60 + [40.0] * 10 + [30.0] * 5})
    kq = tinh_hoa_gio(df, nguong=25, so_huong=8)
    dong, tay = kq["huong"][2], kq["huong"][6]
    assert dong["tan_suat"] > tay["tan_suat"]                 # gió Đông nhiều hơn (F_k lớn)
    assert tay["xac_suat_vuot"] == 1.0 and dong["xac_suat_vuot"] == 0.0   # nhưng gió Tây mới mang bụi (P_k lớn)
    assert kq["lang_gio"]["so_gio"] == 5 and kq["lang_gio"]["xac_suat_vuot"] == 1.0
    assert abs(sum(h["tan_suat"] for h in kq["huong"]) + kq["lang_gio"]["tan_suat"] - 100) < 0.1


def _mo_hinh():
    import train_model as tm
    from test_train_model import _gia
    df = tm.tao_dac_trung(_gia(400))
    kq, mos = tm.danh_gia(df, nhanh=True)
    return mos["du_bao_ngay_mai"], {"features_du_bao_ngay_mai": tm.FEATURES_DU_BAO,
                                    "du_bao_metrics": kq["mo_hinh"]["du_bao_ngay_mai"]["random_forest"], "danh_gia": kq}, _gia


def test_bay_ngay_tinh_tu_ngay_he_thong_va_bu_khoang_trong():
    model, meta, _gia = _mo_hinh()
    raw = _gia(60)[["ngay_do", "pm25_mean"]]
    hom_nay = raw["ngay_do"].iloc[-1] + pd.Timedelta(days=3)          # dữ liệu trễ 3 ngày so với ngày hệ thống
    kq, th = pr.du_bao_tu_chuoi(raw, model, meta, 7, hom_nay)
    assert [x["ngay"] for x in kq] == [str((hom_nay + pd.Timedelta(days=i)).date()) for i in range(1, 8)]
    assert th["so_ngay_bu"] == 3 and kq[0]["bac_du_bao"] == 4 and not kq[0]["da_kiem_chung"]
    rong = [x["khoang_80"]["cao"] - x["khoang_80"]["thap"] for x in kq]
    assert all(b >= a - 1e-9 for a, b in zip(rong, rong[1:]))            # khoảng nới rộng theo số bước


def test_xac_suat_vuot_hop_ly():
    pv = {"q10": -6.5, "q90": 7.7}
    thap, cao = pr.xac_suat_vuot(10, pv), pr.xac_suat_vuot(40, pv)
    assert 0 <= thap["who_15"] < cao["who_15"] <= 1 and thap["qcvn_45"] < cao["qcvn_45"]
    assert pr.xac_suat_vuot(30, pv, k=2)["qcvn_45"] > pr.xac_suat_vuot(30, pv)["qcvn_45"]   # xa hơn → bất định hơn


def test_xu_huong_theo_thang():
    ngay = pd.date_range("2022-01-01", "2026-11-17", freq="D")
    pm = 25 + 8 * np.cos((ngay.month.values - 1) / 12 * 2 * np.pi) + np.random.default_rng(0).normal(0, 2, len(ngay))
    kq = pr.du_bao_theo_thang_tu_chuoi(pd.DataFrame({"ngay_do": ngay, "pm25_mean": pm}), 3, "2026-11-18")
    assert [x["thang"] for x in kq["thang"]] == ["2026-12", "2027-01", "2027-02"]
    assert kq["thang"][1]["pm25"] > 28                                     # tháng 1 (mùa khô) cao hơn trung bình
    assert kq["danh_gia"]["so_thang_thu"] > 30 and kq["danh_gia"]["ky_nang"] > 0
