import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "data_pipeline"))
import doi_chieu_tram_that as dc


def test_bias_va_phan_loai():
    ngay = pd.date_range("2025-01-01", periods=60)
    that = pd.Series(np.linspace(10, 70, 60), index=ngay)
    cams = that + 8                                  # CAMS cao hơn đúng 8
    kq = dc.so_sanh(that, cams)
    assert abs(kq["bias_cams_tru_that"] - 8) < 1e-9 and abs(kq["MAE"] - 8) < 1e-9 and kq["pearson_r"] > 0.999
    assert kq["ngưỡng"]["QCVN_05_2023"]["bao_nham"] > 0 and kq["ngưỡng"]["QCVN_05_2023"]["bo_sot"] == 0


def test_trung_binh_ngay_loai_ngay_thieu_gio():
    gio = pd.date_range("2025-01-01", periods=24 + 5, freq="h")
    d = dc.trung_binh_ngay(pd.DataFrame({"thoi_gian": gio, "pm25": 20.0}))
    assert len(d) == 1                               # ngày thứ hai chỉ có 5 giờ → loại


def test_it_ngay_thi_bao_loi():
    s = pd.Series([1.0] * 5, index=pd.date_range("2025-01-01", periods=5))
    try:
        dc.so_sanh(s, s); assert False
    except ValueError:
        pass
