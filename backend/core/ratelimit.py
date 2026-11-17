"""Giới hạn tần suất (chống dò mật khẩu, chống spam), đếm trong bộ nhớ của tiến trình máy chủ.

1. Đăng nhập theo cặp (email, IP): 5 lần sai trong 15 phút thì khóa phần còn lại của 15 phút đó.
2. Đăng nhập theo email trên MỌI IP: 20 lần sai trong 15 phút thì khóa tài khoản tạm thời
   (chặn dò mật khẩu phân tán từ nhiều địa chỉ IP).
3. Bộ đếm chung `vuot_gioi_han(nhom, khoa, toi_da, cua_so)` cho đăng ký, gửi OTP, nhập mã 2 lớp...

Chạy 1 tiến trình (uvicorn 1 worker) là đủ cho quy mô đồ án; chạy nhiều worker thì nên chuyển sang Redis.
"""

from core import config  # noqa: F401
import threading
import time

TOI_DA = 5
CUA_SO_GIAY = 15 * 60
TOI_DA_THEO_EMAIL = 20
_loi = {}
_dem = {}
_khoa = threading.Lock()


def _don(bang, khoa, now, cua_so=CUA_SO_GIAY):
    bang[khoa] = [t for t in bang.get(khoa, []) if now - t < cua_so]
    if not bang[khoa]:
        bang.pop(khoa, None)
    return bang.get(khoa, [])


def con_lai_giay(email: str, ip: str, now: float = None) -> int:
    """Số giây còn bị khóa (0 nếu chưa bị khóa)."""
    now = time.time() if now is None else now
    with _khoa:
        ds = _don(_loi, (email, ip), now)
        if len(ds) >= TOI_DA:
            return int(CUA_SO_GIAY - (now - ds[0])) + 1
        de = _don(_loi, ("*", email), now)
        if len(de) >= TOI_DA_THEO_EMAIL:
            return int(CUA_SO_GIAY - (now - de[0])) + 1
    return 0


def ghi_that_bai(email: str, ip: str, now: float = None):
    now = time.time() if now is None else now
    with _khoa:
        _don(_loi, (email, ip), now)
        _loi.setdefault((email, ip), []).append(now)
        _don(_loi, ("*", email), now)
        _loi.setdefault(("*", email), []).append(now)


def xoa(email: str, ip: str):
    """Đăng nhập đúng: xóa bộ đếm của cặp (email, IP). Bộ đếm theo email giữ nguyên tới khi hết cửa sổ."""
    with _khoa:
        _loi.pop((email, ip), None)


def vuot_gioi_han(nhom: str, khoa: str, toi_da: int, cua_so_giay: int, now: float = None) -> int:
    """Ghi nhận 1 lần gọi; trả về số giây phải chờ nếu đã vượt `toi_da` lần trong `cua_so_giay` (0 nếu còn được phép)."""
    now = time.time() if now is None else now
    k = (nhom, khoa)
    with _khoa:
        ds = _don(_dem, k, now, cua_so_giay)
        if len(ds) >= toi_da:
            return int(cua_so_giay - (now - ds[0])) + 1
        _dem.setdefault(k, []).append(now)
    return 0
