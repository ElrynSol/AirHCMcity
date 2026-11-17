"""Kiem thu don vi cho ham tinh AQI tong hop (VN_AQI theo QD 1459/QD-TCMT).

Chay tu THU MUC GOC du an:
    python -m pytest tests/test_aqi.py -q
(can: pip install pytest; conftest.py da them ml/ vao sys.path de import tinh_aqi)

Cac test bam theo bang nguong PM2.5 (trung binh 24h) cua VN_AQI:
    PM2.5 = 25  -> AQI = 50   (ranh gioi Tot / Trung binh)
    PM2.5 = 50  -> AQI = 100  (ranh gioi Trung binh / Kem)
    PM2.5 = 80  -> AQI = 150  (ranh gioi Kem / Xau)
Tai dung cac moc nong do nay, cong thuc noi suy cho ra dung gia tri AQI bien.
"""
import sys
from pathlib import Path

import pytest

# conftest.py da them ml/ vao sys.path; them lai o day de chay doc lap cung duoc
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ml"))
from tinh_aqi import tinh_aqi_tong_hop, phan_loai_aqi  # noqa: E402


def _aqi(pm25=None, pm10=None, o3=None):
    return tinh_aqi_tong_hop(pm25=pm25, pm10=pm10, o3=o3)[0]


# ---------- Cau truc tra ve ----------
def test_tra_ve_la_tuple_aqi_va_chat():
    kq = tinh_aqi_tong_hop(pm25=30)
    assert isinstance(kq, tuple) and len(kq) == 2
    aqi, chat = kq
    assert isinstance(aqi, (int, float)) and aqi >= 0
    assert isinstance(chat, str) and chat


def test_khong_co_du_lieu_tra_ve_none():
    assert tinh_aqi_tong_hop() == (None, None)


# ---------- Cac moc nguong PM2.5 theo QD 1459 ----------
@pytest.mark.parametrize("pm25, aqi_mong_doi", [(0, 0), (25, 50), (50, 100), (80, 150)])
def test_moc_nguong_pm25(pm25, aqi_mong_doi):
    assert _aqi(pm25=pm25) == pytest.approx(aqi_mong_doi, abs=1)


# ---------- Tinh don dieu: nong do cao hon thi AQI khong giam ----------
def test_pm25_cang_cao_aqi_cang_lon():
    gia_tri = [_aqi(pm25=x) for x in (10, 30, 60, 100, 200)]
    assert all(b >= a for a, b in zip(gia_tri, gia_tri[1:]))


# ---------- Tong hop lay chi so lon nhat giua cac chat ----------
def test_tong_hop_lay_chat_o_nhiem_cao_nhat():
    # PM2.5 = 100 (o nhiem nang) di kem PM10 = 10 (rat sach): AQI do PM2.5 quyet dinh
    aqi_ca_hai, chat = tinh_aqi_tong_hop(pm25=100, pm10=10)
    assert aqi_ca_hai == pytest.approx(_aqi(pm25=100), abs=1)
    assert chat == "PM2.5"


# ---------- Phan loai 6 muc ----------
def test_phan_loai_dung_sau_muc():
    assert phan_loai_aqi(25) == "Tốt"
    assert phan_loai_aqi(75) == "Trung bình"
    assert phan_loai_aqi(125) == "Kém"
    assert phan_loai_aqi(175) == "Xấu"
    assert phan_loai_aqi(250) == "Rất xấu"
    assert phan_loai_aqi(350) == "Nguy hại"


# ---------- Bang nguong day du theo QD 1459 (bo sung v4.0) ----------
from tinh_aqi import tinh_aqi_o3, muc_aqi, mau_aqi, THANG_AQI, thang_do_cong_khai  # noqa: E402


@pytest.mark.parametrize("pm25, aqi_mong_doi", [(150, 200), (250, 300), (350, 400), (500, 500), (900, 500)])
def test_moc_nguong_pm25_muc_cao(pm25, aqi_mong_doi):
    assert _aqi(pm25=pm25) == aqi_mong_doi


@pytest.mark.parametrize("pm10, aqi_mong_doi", [(50, 50), (150, 100), (250, 150), (350, 200), (420, 300), (500, 400), (600, 500)])
def test_moc_nguong_pm10(pm10, aqi_mong_doi):
    assert _aqi(pm10=pm10) == aqi_mong_doi


@pytest.mark.parametrize("o3, kieu, aqi_mong_doi", [(100, "8h", 50), (120, "8h", 100), (170, "8h", 150), (210, "8h", 200),
                                                    (400, "8h", 300), (160, "1h", 50), (200, "1h", 100), (1000, "1h", 400)])
def test_moc_nguong_o3(o3, kieu, aqi_mong_doi):
    assert tinh_aqi_o3(o3, kieu) == aqi_mong_doi


def test_o3_8h_vuot_bang_chuyen_sang_bang_1h():
    assert tinh_aqi_o3(900, "8h") == tinh_aqi_o3(900, "1h") == 350


def test_bat_buoc_co_bui_moi_tinh_aqi():
    assert tinh_aqi_tong_hop(o3=300) == (None, None)
    assert tinh_aqi_tong_hop(pm25=10, o3=300)[1] == "O3"


def test_gia_tri_khong_hop_le():
    assert tinh_aqi_tong_hop(pm25=float("nan")) == (None, None)
    assert tinh_aqi_tong_hop(pm25=-5) == (None, None)


def test_thang_mau_chuan_qd_1459():
    assert [m["mau"] for m in THANG_AQI] == ["#00e400", "#ffff00", "#ff7e00", "#ff0000", "#8f3f97", "#7e0023"]
    assert muc_aqi(50)["muc"] == "Tốt" and muc_aqi(51)["muc"] == "Trung bình"
    assert muc_aqi(301)["muc"] == "Nguy hại" and muc_aqi(700)["muc"] == "Nguy hại"
    assert mau_aqi(None) == "#98a2b3"
    assert all(m["nguoi_binh_thuong"] and m["nhom_nhay_cam"] for m in THANG_AQI)
    assert len(thang_do_cong_khai()["muc"]) == 6
