import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import train_diem as td
import train_model as tm
from services import ban_do_nhiet as bd


def _dai(n_tram=5, n=300, seed=1):
    r = np.random.default_rng(seed)
    nen = 30 + np.cumsum(r.normal(0, 2, n)) * 0.3
    cac = []
    for t in range(n_tram):
        cac.append(pd.DataFrame({"tram_id": 100 + t, "ngay_do": pd.date_range("2025-01-01", periods=n),
                                 "pm25_mean": np.abs(nen + t * 2 + r.normal(0, 3, n)) + 5}))
    return pd.concat(cac, ignore_index=True)


def test_idw_tai_diem_tram_bang_gia_tri_tram_va_nam_trong_khoang():
    lat = np.array([10.7, 10.8, 10.9]); lon = np.array([106.6, 106.7, 106.8]); v = np.array([10., 20., 40.])
    assert abs(float(bd.noi_suy_idw(lat, lon, v, np.array(10.8), np.array(106.7))) - 20) < 0.05
    glat, glon = np.meshgrid(np.linspace(10.6, 11, 9), np.linspace(106.5, 106.9, 9), indexing="ij")
    z = bd.noi_suy_idw(lat, lon, v, glat, glon)
    assert z.min() >= 10 - 1e-6 and z.max() <= 40 + 1e-6 and z.shape == glat.shape


def test_bo_mot_tram():
    lat = np.linspace(10.6, 10.95, 8); lon = np.linspace(106.5, 106.85, 8); v = np.linspace(10, 40, 8)   # gradient tuyến tính
    r = bd.sai_so_bo_mot_tram(lat, lon, v)
    assert r["so_tram"] == 8 and r["RMSE_idw"] >= 0 and r["ky_nang_so_voi_trung_binh"] > 0
    assert bd.sai_so_bo_mot_tram(lat[:2], lon[:2], v[:2]) is None


def test_canh_bao_khi_cac_tram_gan_nhu_bang_nhau():
    chenh, cb = bd.canh_bao_khong_gian([30.0, 30.4, 30.2], 6.0)
    assert cb and chenh < 1
    assert bd.canh_bao_khong_gian([10, 40], 6.0)[1] == []


def test_huan_luyen_va_du_bao_cac_diem():
    dai = _dai()
    kq, model = td.danh_gia_diem(dai, nhanh=True)
    assert kq["so_tram"] == 5 and "ky_nang_so_voi_hom_qua" in kq["random_forest"] and "khong_gian" in kq
    ok, bo, ngay = bd.du_bao_cac_diem(dai, model, kq, 2, dai["ngay_do"].max())
    assert len(ok) == 5 and all(len(v) == 2 for v in ok.values()) and len(ngay) == 2
    # hôm nay quá xa dữ liệu → mọi trạm bị bỏ với lý do rõ
    ok2, bo2, _ = bd.du_bao_cac_diem(dai, model, kq, 1, dai["ngay_do"].max() + pd.Timedelta(days=20))
    assert not ok2 and len(bo2) == 5


def test_aqi_luoi_gop_gia_tri():
    n = []
    def f(pm25): n.append(pm25); return (int(pm25 * 2), "PM2.5")
    out = bd.aqi_luoi(np.array([[10.01, 10.02], [10.04, 20.0]]), f)
    assert out.shape == (2, 2) and len(n) == 2


def test_danh_gia_vung_bo_phuong_xa_tram_khi_xep_hang():
    """Đánh giá theo vùng: phường cách trạm > 15 km (ngoại suy) không được xếp 'cao nhất/thấp nhất'."""
    from services import ban_do_nhiet as bd
    from services.ranh_gioi import do_tin_cay_theo_km
    assert [do_tin_cay_theo_km(x) for x in (2, 10, 40, None)] == ["cao", "trung_binh", "thap", "khong_ro"]
    f_aqi = lambda pm25: (round(pm25 * 2), "PM2.5")
    lat, lon, v = np.array([10.80, 10.70]), np.array([106.70, 106.60]), np.array([20.0, 30.0])
    phuong = [  # phường xa trạm nằm sát trạm 30 → giá trị cao nhất nhưng phải bị loại khỏi xếp hạng
        {"ma": "1", "ten_day_du": "Gần A", "khu_vuc": "K", "lat": 10.80, "lon": 106.70, "do_tin_cay": "cao"},
        {"ma": "2", "ten_day_du": "Xa", "khu_vuc": "K", "lat": 10.70, "lon": 106.60, "do_tin_cay": "thap"},
        {"ma": "3", "ten_day_du": "Giữa", "khu_vuc": "K", "lat": 10.76, "lon": 106.66, "do_tin_cay": "trung_binh"}]
    tung, tom = bd.danh_gia_vung(phuong, lat, lon, v, f_aqi)
    assert len(tung) == 3 and tom[0]["so_phuong"] == 3 and tom[0]["so_phuong_xep_hang"] == 2
    assert tom[0]["phuong_cao_nhat"] == "Giữa" and tom[0]["so_phuong_tin_cay_thap"] == 1
