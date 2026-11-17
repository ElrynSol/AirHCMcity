"""Kiểm thử module IoT (không cần CSDL hay broker MQTT):
- lọc giá trị cảm biến, mã thiết bị và tên thiết bị gửi qua broker công cộng
- cảnh báo vượt ngưỡng có trễ (không báo dồn dập) và thời gian chờ giữa 2 lần báo
- gói tin sai khóa / sai mã / thiếu số liệu bụi bị loại trước khi chạm CSDL
- bảng ngưỡng AQI trong firmware ESP32 trùng với ml/tinh_aqi.py (QĐ 1459)

Chạy từ thư mục gốc:  python -m pytest tests/test_iot.py -q
"""
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import iot
from tinh_aqi import BANG_AQI_PM25, BANG_AQI_PM10

GOC = Path(__file__).resolve().parent.parent


@pytest.fixture
def su_kien(monkeypatch):
    """Bắt các sự kiện phát ra và tắt ghi nhật ký vào CSDL."""
    ds = []
    monkeypatch.setattr(iot.events, "publish", lambda chu_de, du_lieu=None: ds.append((chu_de, du_lieu)))
    monkeypatch.setattr(iot.logbus, "ghi", lambda *a, **k: None)
    iot._dang_vuot.clear()
    iot._lan_bao_cuoi.clear()
    return ds


# ---------- Lọc dữ liệu đầu vào ----------
@pytest.mark.parametrize("gt, ten, mong_doi", [
    (35.27, "pm25", 35.27), ("41", "pm10", 41.0), (-1, "pm25", None), (5000, "pm25", None),
    (float("nan"), "pm25", None), ("abc", "do_am", None), (None, "nhiet_do", None), (101, "do_am", None)])
def test_loc_gia_tri_cam_bien(gt, ten, mong_doi):
    assert iot._so(gt, ten) == mong_doi


@pytest.mark.parametrize("ma, hop_le", [("IOT01", True), ("tram_ao-2", True), ("a'b", False), ("<x>", False), ("", False), ("A" * 31, False)])
def test_ma_thiet_bi(ma, hop_le):
    assert bool(iot.MA_HOP_LE.match(ma)) is hop_le


def test_ten_thiet_bi_bo_ky_tu_html_va_dieu_khien():
    assert iot._ten_an_toan('<img src=x onerror=alert(1)>Trạm "A"', "X") == "img src=x onerror=alert(1)Trạm A"
    assert iot._ten_an_toan(chr(0) + chr(7), "X2") == "Trạm IoT X2"
    assert len(iot._ten_an_toan("a" * 200, "X")) == 80


# ---------- Cảnh báo vượt ngưỡng ----------
def _tb(pm25=60.0, pm10=90.0):
    return SimpleNamespace(pm25=pm25, pm10=pm10)


def test_canh_bao_co_tre_va_thoi_gian_cho(su_kien, monkeypatch):
    gio = [1000.0]
    monkeypatch.setattr(iot.time, "time", lambda: gio[0])
    ng = iot.NGUONG_AQI

    for aqi in (ng - 20, ng + 10, ng + 30, ng - 5):          # dưới → vượt (báo 1 lần) → vẫn vượt → chưa xuống đủ sâu
        iot._kiem_tra_nguong("IOT01", aqi, "PM2.5", _tb(), {})
    assert [c for c, _ in su_kien] == ["iot.vuot_nguong"]
    assert su_kien[0][1]["aqi"] == ng + 10 and su_kien[0][1]["nguong"] == ng

    iot._kiem_tra_nguong("IOT01", ng - 15, "PM2.5", _tb(), {})   # xuống dưới ngưỡng − 10 → sẵn sàng báo lại
    gio[0] += 30
    iot._kiem_tra_nguong("IOT01", ng + 5, "PM2.5", _tb(), {})    # vượt lại nhưng mới 30 giây → chưa báo
    assert len(su_kien) == 1
    gio[0] += 200
    iot._kiem_tra_nguong("IOT01", ng + 5, "PM2.5", _tb(), {})    # quá 2 phút → báo
    assert len(su_kien) == 2


def test_khong_co_aqi_thi_khong_bao(su_kien):
    iot._kiem_tra_nguong("IOT01", None, None, _tb(None, None), {})
    assert su_kien == []


# ---------- Gói tin bị loại trước khi ghi CSDL ----------
@pytest.mark.parametrize("topic, goi", [
    ("airhcm/x/tram/IOT01/do", {"khoa": "sai-khoa", "pm25": 30}),
    ("airhcm/x/tram/a'b/do", {"khoa": iot.KHOA_THIET_BI, "pm25": 30}),
    ("airhcm/x/tram/IOT01/do", {"khoa": iot.KHOA_THIET_BI, "nhiet_do": 30}),
    ("airhcm/x/tram/IOT01/do", {"khoa": iot.KHOA_THIET_BI, "pm25": -5, "pm10": 99999}),
])
def test_goi_tin_khong_hop_le_bi_loai(topic, goi, monkeypatch, su_kien):
    monkeypatch.setattr(iot.engine, "begin", lambda: (_ for _ in ()).throw(AssertionError("không được ghi CSDL")))
    truoc = iot.trang_thai["so_tin_bo"]
    iot._khi_nhan_tin(None, None, SimpleNamespace(topic=topic, payload=json.dumps(goi).encode()))
    assert iot.trang_thai["so_tin_bo"] == truoc + 1
    assert su_kien == []


# ---------- Firmware ESP32 dùng đúng bảng ngưỡng QĐ 1459 ----------
def _mang_firmware(ten):
    src = (GOC / "iot" / "wokwi_tram" / "wokwi_tram.ino").read_text(encoding="utf-8")
    m = re.search(r"\b" + ten + r"\[\]\s*=\s*\{([^}]*)\}", src)
    return [float(x) for x in m.group(1).split(",")]


def _moc(bang):
    return [bang[0][0]] + [d[1] for d in bang]


def test_bang_nguong_firmware_trung_tinh_aqi():
    assert _mang_firmware("BP25") == _moc(BANG_AQI_PM25)
    assert _mang_firmware("BP10") == _moc(BANG_AQI_PM10)
    assert _mang_firmware("I_AQI") == [0, 50, 100, 150, 200, 300, 400, 500]


def test_mau_firmware_trung_thang_chuan_qd1459():
    from tinh_aqi import THANG_AQI
    src = (GOC / "iot" / "wokwi_tram" / "wokwi_tram.ino").read_text(encoding="utf-8")
    mau = re.search(r"MAU_MUC\[\]\s*=\s*\{([^}]*)\}", src).group(1)
    assert [f"#{int(x, 16):06x}" for x in mau.split(",")] == [m["mau"] for m in THANG_AQI]
