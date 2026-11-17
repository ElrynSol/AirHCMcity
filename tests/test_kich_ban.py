import sys
from pathlib import Path
import numpy as np, pandas as pd, pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import train_model as tm
from services import kich_ban as kb
from test_train_model import _gia


@pytest.fixture(scope="module")
def nen():
    df = tm.tao_dac_trung(_gia(500))
    kq, mos = tm.danh_gia(df, nhanh=True)
    hang, ngay = kb.tao_hang_nen(df, tm.FEATURES)
    mh = {"random_forest": mos["uoc_luong_trong_ngay"], "tuyen_tinh": mos["uoc_luong_tuyen_tinh"]}
    return mh, hang, kq["khoang_dac_trung"]


def test_khong_doi_thi_chenh_lech_bang_0(nen):
    mh, hang, kh = nen
    r = kb.chay_kich_ban(mh, tm.FEATURES, hang, kh, {})
    assert r["chenh_lech"] == {"random_forest": 0.0, "tuyen_tinh": 0.0}


def test_gia_tri_ngoai_khoang_bi_kep(nen):
    mh, hang, kh = nen
    r = kb.chay_kich_ban(mh, tm.FEATURES, hang, kh, {"o3_mean": 10_000})
    assert r["bien_bi_gioi_han"] == ["o3_mean"]
    h2, _ = kb.ap_dung_thay_doi(hang, {"o3_mean": 10_000}, kh)
    assert h2["o3_mean"] == pytest.approx(kh["o3_mean"]["p99"])


def test_bien_la_bi_tu_choi(nen):
    mh, hang, kh = nen
    with pytest.raises(ValueError):
        kb.chay_kich_ban(mh, tm.FEATURES, hang, kh, {"pm25_lag1": 1})


def test_duong_nhay_du_8_bien_va_tich_nhietdo_doam_cap_nhat(nen):
    mh, hang, kh = nen
    d = kb.duong_nhay(mh, tm.FEATURES, hang, kh, so_diem=5)
    assert set(d) == set(kb.BIEN) and all(len(v) == 5 for v in d.values())
    h2, _ = kb.ap_dung_thay_doi(hang, {"nhiet_do_mean": kh["nhiet_do_mean"]["p99"]}, kh)
    assert h2["nhietdo_x_doam"] == pytest.approx(h2["nhiet_do_mean"] * h2["do_am_mean"])


def test_danh_gia_kich_ban_va_do_tin_cay():
    """Đánh giá kịch bản: nhận xét đúng chiều, tin cậy thấp khi hai mô hình trái chiều hoặc thay đổi nhỏ hơn sai số."""
    from services import kich_ban as kb
    from tinh_aqi import muc_aqi, tinh_aqi_tong_hop
    cs = {"random_forest": {"RMSE": 5.0, "phan_vi_sai_so": {"q10": -2.0, "q90": 8.0}}, "hoi_quy_tuyen_tinh": {"RMSE": 5.0}}
    def kq(rf0, tt0, rf1, tt1, kep=()):
        return {"nen": {"random_forest": rf0, "tuyen_tinh": tt0}, "kich_ban": {"random_forest": rf1, "tuyen_tinh": tt1},
                "chenh_lech": {"random_forest": rf1 - rf0, "tuyen_tinh": tt1 - tt0}, "bien_bi_gioi_han": list(kep),
                "hai_mo_hinh_trai_chieu": (rf1 - rf0) * (tt1 - tt0) < 0}
    tang = kb.danh_gia(kq(25, 25, 34, 32), cs, muc_aqi, tinh_aqi_tong_hop)
    assert tang["chenh_lech"] > 0 and "tăng" in tang["nhan_xet"][0] and tang["tin_cay"]["muc"] == "cao"
    assert tang["tin_cay"]["khoang_80"] == {"thap": 32.0, "cao": 42.0}
    assert kb.danh_gia(kq(25, 25, 27, 23), cs, muc_aqi, tinh_aqi_tong_hop)["tin_cay"]["muc"] == "thap"     # trái chiều
    assert kb.danh_gia(kq(25, 25, 25.5, 25.4), cs, muc_aqi, tinh_aqi_tong_hop)["tin_cay"]["muc"] == "thap"  # nhỏ hơn sai số
    vuot = kb.danh_gia(kq(45, 45, 60, 58), cs, muc_aqi, tinh_aqi_tong_hop)
    assert any("Vượt ngưỡng QCVN" in t for t in vuot["nhan_xet"])
    assert set(kb.KICH_BAN_MAU) >= {"gio_manh", "gio_lang", "mua_lon"}
