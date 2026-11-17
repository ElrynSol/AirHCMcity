"""Cầu nối bus sự kiện nội bộ → trình duyệt bằng Server-Sent Events (SSE, text/event-stream).

Bus sự kiện (core/events.py) chạy handler trong luồng nền; mỗi trình duyệt đang mở /api/v1/su-kien có một
asyncio.Queue trên vòng lặp của máy chủ. phat() được gọi từ luồng nền nên đẩy vào hàng đợi bằng
loop.call_soon_threadsafe. Hàng đợi đầy (trình duyệt chậm) thì bỏ sự kiện cũ, không chặn bus.

Chỉ đẩy dữ liệu công khai (không email, không thông tin tài khoản).
"""

import asyncio
import json
import threading
import time

from core import events

# Không đẩy aqi.vuot_nguong: sự kiện đó phát theo TỪNG người đăng ký (email, ngưỡng riêng) – không công khai được.
CHU_DE_DAY = ("iot.da_nhan", "iot.vuot_nguong", "du_lieu.da_nap", "dong_bo.xong")
_nguoi_nghe = {}          # queue -> (loop, tập chủ đề muốn nhận | None = tất cả)
_khoa = threading.Lock()
_da_dang_ky = False
thong_ke = {"da_day": 0, "bo_qua": 0}


def _dua_vao(q, item):
    try:
        q.put_nowait(item)
    except asyncio.QueueFull:
        try:
            q.get_nowait()          # bỏ sự kiện cũ nhất, giữ sự kiện mới
            q.put_nowait(item)
        except Exception:
            thong_ke["bo_qua"] += 1


def phat(chu_de: str, du_lieu: dict):
    item = {"chu_de": chu_de, "du_lieu": du_lieu, "t": time.time()}
    with _khoa:
        ds = list(_nguoi_nghe.items())
    for q, (loop, loc) in ds:
        if loc and chu_de not in loc:
            continue
        try:
            loop.call_soon_threadsafe(_dua_vao, q, item)
            thong_ke["da_day"] += 1
        except RuntimeError:        # vòng lặp đã đóng (máy chủ đang tắt / nạp lại)
            pass


def dang_ky(q, loop, loc=None):
    with _khoa:
        _nguoi_nghe[q] = (loop, set(loc) if loc else None)


def huy(q):
    with _khoa:
        _nguoi_nghe.pop(q, None)


def so_ket_noi() -> int:
    with _khoa:
        return len(_nguoi_nghe)


def khoi_dong():
    """Đăng ký 1 lần: mọi chủ đề công khai trên bus đều được chuyển tiếp cho trình duyệt."""
    global _da_dang_ky
    if _da_dang_ky:
        return
    for cd in CHU_DE_DAY:
        events.subscribe(cd, (lambda c: (lambda d: phat(c, _loc_cong_khai(c, d))))(cd))
    _da_dang_ky = True


def _loc_cong_khai(chu_de, d):
    """Bỏ trường nhạy cảm trước khi đẩy ra trình duyệt."""
    d = dict(d or {})
    for k in ("email", "dk_id", "nguoi_dung"):
        d.pop(k, None)
    return json.loads(json.dumps(d, ensure_ascii=False, default=str))
