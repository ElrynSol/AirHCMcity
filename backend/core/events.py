"""Bus sự kiện nội bộ (mô hình publish/subscribe) chạy trong tiến trình FastAPI.

Thành phần phát (producer) chỉ gọi publish(chu_de, du_lieu); các thành phần xử lý (consumer)
đăng ký bằng subscribe(chu_de, ham). Mỗi sự kiện được xử lý bởi 1 luồng nền, lỗi của consumer
được ghi nhật ký và không ảnh hưởng producer.

Đây là bản gọn của mô hình Kafka (topic - producer - consumer). Giao diện publish/subscribe được
giữ nguyên nên khi mở rộng sang cảm biến thật có thể thay phần bên trong bằng Kafka mà không đổi
các consumer (xem sơ đồ kiến trúc mở rộng).
"""

from core import config  # noqa: F401
import queue
import threading
import time
from collections import defaultdict

from core import logbus

_cac_handler = defaultdict(list)
_hang_doi: "queue.Queue" = queue.Queue()
_thong_ke = defaultdict(int)
_luong = None
_khoa = threading.Lock()


def subscribe(chu_de: str, ham):
    _cac_handler[chu_de].append(ham)


def publish(chu_de: str, du_lieu: dict = None):
    _thong_ke[chu_de] += 1
    _hang_doi.put((chu_de, du_lieu or {}, time.time()))


def thong_ke() -> dict:
    return {"cho_xu_ly": _hang_doi.qsize(), "so_su_kien": dict(_thong_ke),
            "chu_de": {k: len(v) for k, v in _cac_handler.items()}}


def _worker():
    while True:
        chu_de, du_lieu, _t = _hang_doi.get()
        for ham in _cac_handler.get(chu_de, []):
            try:
                ham(du_lieu)
            except Exception as exc:
                logbus.ghi("ERROR", "event_bus", chu_de, f"{ham.__name__}: {type(exc).__name__}: {exc}")


def khoi_dong():
    """Bật luồng xử lý sự kiện (gọi 1 lần khi ứng dụng khởi động)."""
    global _luong
    with _khoa:
        if _luong is None:
            _luong = threading.Thread(target=_worker, name="event-bus", daemon=True)
            _luong.start()
