"""Kiểm thử logic đồng bộ tự động (không cần CSDL, không gọi API):
- chọn khoảng ngày cần tải, tự lấy bù ngày thiếu, giới hạn bù
- quyết định khi nào máy chủ tự kích hoạt đồng bộ (lịch hằng ngày, dữ liệu cũ, tránh thử lại dồn dập)

Chạy từ thư mục gốc:  python -m pytest tests/test_dong_bo.py -q
"""
from datetime import date, datetime, timedelta

import dong_bo_hang_ngay as db
from services import dong_bo as lich

HOM_NAY = date(2026, 10, 23)
D = lambda s: date.fromisoformat(s)


# ---------- Khoảng ngày cần tải ----------
def test_binh_thuong_lam_moi_3_ngay_gan_nhat():
    (om_tu, om_den), gee = db.tinh_khoang(HOM_NAY, D("2026-10-22"), D("2026-10-17"))
    assert (om_tu, om_den) == (D("2026-10-20"), D("2026-10-22"))      # hôm qua − 2 → hôm qua
    assert gee == (D("2026-10-18"), D("2026-10-18"))                    # vệ tinh tới hôm nay − 5


def test_lo_lich_nhieu_ngay_thi_tu_lay_bu():
    (om_tu, om_den), _ = db.tinh_khoang(HOM_NAY, D("2026-10-14"), D("2026-10-01"))
    assert (om_tu, om_den) == (D("2026-10-15"), D("2026-10-22"))


def test_bu_toi_da_60_ngay_va_gee_30_ngay():
    (om_tu, _), (gee_tu, _) = db.tinh_khoang(HOM_NAY, D("2025-01-01"), D("2025-01-01"))
    assert om_tu == D("2026-10-22") - timedelta(days=60)
    assert gee_tu == HOM_NAY - timedelta(days=30)


def test_csdl_trong():
    (om_tu, om_den), gee = db.tinh_khoang(HOM_NAY, None, None)
    assert om_den == D("2026-10-22") and om_tu == D("2026-09-22")
    assert gee is not None and gee[1] == D("2026-10-18")


def test_gee_da_du_thi_bo_qua():
    _, gee = db.tinh_khoang(HOM_NAY, D("2026-10-22"), D("2026-10-18"))
    assert gee is None


# ---------- Khi nào máy chủ tự đồng bộ ----------
GIO = (7, 45)
SANG = datetime(2026, 10, 23, 9, 0)


def test_qua_gio_hen_chua_chay_hom_nay_thi_chay():
    assert lich.quyet_dinh(SANG, D("2026-10-22"), datetime(2026, 10, 22, 7, 46), datetime(2026, 10, 22, 7, 49), GIO)


def test_da_thanh_cong_hom_nay_va_du_du_lieu_thi_khong_chay():
    assert lich.quyet_dinh(SANG, D("2026-10-22"), datetime(2026, 10, 23, 7, 30), datetime(2026, 10, 23, 7, 33), GIO) is None


def test_chua_toi_gio_hen_nhung_thieu_du_lieu_thi_bu_ngay():
    som = datetime(2026, 10, 23, 6, 0)
    ly_do = lich.quyet_dinh(som, D("2026-10-20"), datetime(2026, 10, 22, 7, 46), datetime(2026, 10, 22, 7, 49), GIO)
    assert ly_do and "2026-10-20" in ly_do


def test_khong_thu_lai_don_dap_trong_3_gio():
    # nguồn chưa có số liệu hôm qua: vừa thử 1 giờ trước thì chưa thử lại
    assert lich.quyet_dinh(SANG, D("2026-10-21"), SANG - timedelta(hours=1), SANG - timedelta(hours=1), GIO) is None
    assert lich.quyet_dinh(SANG, D("2026-10-21"), SANG - timedelta(hours=4), SANG - timedelta(hours=4), GIO)


def test_chua_dong_bo_lan_nao():
    assert lich.quyet_dinh(SANG, None, None, None, GIO)
