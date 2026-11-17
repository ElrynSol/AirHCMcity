"""Kiểm thử đơn vị cho phần v3 (không cần mở server).
Chạy từ thư mục backend:  python -m pytest ../tests/test_v3.py -q   (cần: pip install pytest)"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from core import ratelimit, events  # noqa: E402
from services import cdc  # noqa: E402


def test_khoa_sau_5_lan_sai():
    e, ip = "t1@x.com", "1.1.1.1"
    ratelimit.xoa(e, ip)
    for _ in range(ratelimit.TOI_DA - 1):
        ratelimit.ghi_that_bai(e, ip)
    assert ratelimit.con_lai_giay(e, ip) == 0
    ratelimit.ghi_that_bai(e, ip)
    assert ratelimit.con_lai_giay(e, ip) > 0


def test_tu_mo_khoa_sau_15_phut():
    e, ip = "t2@x.com", "1.1.1.1"
    ratelimit.xoa(e, ip)
    t0 = 1000.0
    for _ in range(ratelimit.TOI_DA):
        ratelimit.ghi_that_bai(e, ip, now=t0)
    assert ratelimit.con_lai_giay(e, ip, now=t0 + 60) > 0
    assert ratelimit.con_lai_giay(e, ip, now=t0 + ratelimit.CUA_SO_GIAY + 1) == 0


def test_dang_nhap_dung_xoa_bo_dem():
    e, ip = "t3@x.com", "1.1.1.1"
    for _ in range(3):
        ratelimit.ghi_that_bai(e, ip)
    ratelimit.xoa(e, ip)
    assert ratelimit.con_lai_giay(e, ip) == 0


def test_khoa_theo_tung_ip():
    e = "t4@x.com"
    for _ in range(ratelimit.TOI_DA):
        ratelimit.ghi_that_bai(e, "9.9.9.9")
    assert ratelimit.con_lai_giay(e, "9.9.9.9") > 0
    assert ratelimit.con_lai_giay(e, "8.8.8.8") == 0


def test_bus_su_kien_chuyen_den_consumer():
    events.khoi_dong()
    nhan = []
    events.subscribe("test.chu_de", lambda d: nhan.append(d["x"]))
    events.publish("test.chu_de", {"x": 42})
    for _ in range(50):
        if nhan:
            break
        time.sleep(0.05)
    assert nhan == [42]


def test_loi_consumer_khong_lam_chet_bus():
    events.khoi_dong()
    nhan = []

    def hong(_):
        raise RuntimeError("cố ý")
    events.subscribe("test.hong", hong)
    events.subscribe("test.ok", lambda d: nhan.append(1))
    events.publish("test.hong", {})
    events.publish("test.ok", {})
    for _ in range(50):
        if nhan:
            break
        time.sleep(0.05)
    assert nhan == [1]


def test_cdc_dich_thong_bao_thanh_su_kien():
    got = []
    for ct in ("tram.da_tao", "tram.da_sua", "tram.da_xoa", "du_lieu.da_nap"):
        events.subscribe(ct, lambda d, ct=ct: got.append((ct, d.get("op"))))
    events.khoi_dong()
    cdc._chuyen_thanh_su_kien("cdc_tram", '{"op":"INSERT","tram_id":1,"ma_tram":"T1"}')
    cdc._chuyen_thanh_su_kien("cdc_tram", '{"op":"DELETE","tram_id":1,"ma_tram":"T1"}')
    cdc._chuyen_thanh_su_kien("cdc_du_lieu", '{"op":"INSERT","so_dong":3,"tram_ids":[1,2]}')
    cdc._chuyen_thanh_su_kien("cdc_tram", "khong phai json")  # phải bỏ qua, không lỗi
    for _ in range(50):
        if len(got) >= 3:
            break
        time.sleep(0.05)
    assert ("tram.da_tao", "INSERT") in got and ("tram.da_xoa", "DELETE") in got and ("du_lieu.da_nap", "INSERT") in got
