"""Thông báo đẩy (Web Push, chuẩn W3C Push API + VAPID) — cảnh báo AQI chạy nền trên điện thoại/máy tính
kể cả khi đã đóng trang web. Không cần tài khoản Firebase hay dịch vụ bên thứ ba.

Luồng:
1. Trình duyệt xin quyền thông báo → đăng ký với dịch vụ đẩy của trình duyệt (Google/Mozilla/Apple) bằng khóa công khai VAPID
   → gửi "subscription" về máy chủ (bảng dang_ky_day).
2. Luồng nền của máy chủ mỗi 30 phút đọc AQI hiện tại của TP.HCM; AQI ≥ ngưỡng người dùng chọn thì gửi thông báo
   (tối đa 1 lần/6 giờ khi vẫn còn vượt; xuống dưới ngưỡng − 10 thì đặt lại).
3. Service worker (frontend/sw.js) nhận và hiển thị thông báo của hệ điều hành.

Khóa riêng VAPID tự sinh lần đầu ở bi_mat/vapid_private.pem (hoặc đường dẫn VAPID_FILE) — KHÔNG nộp/commit tệp này.
"""

from __future__ import annotations

import base64
import json
import os
import threading
import time
from pathlib import Path

from sqlalchemy import text

from core import config, logbus
from database import engine

CHU_KY_GIAY = int(os.getenv("DAY_CHU_KY_PHUT", "30")) * 60
NHAC_LAI_GIAY = 6 * 3600
_khoa = threading.Lock()
_vapid = None

DDL = """CREATE TABLE IF NOT EXISTS dang_ky_day (
    id SERIAL PRIMARY KEY,
    endpoint TEXT UNIQUE NOT NULL,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    nguoi_dung_id INTEGER REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    nguong_aqi INTEGER NOT NULL DEFAULT 101,
    dang_vuot BOOLEAN NOT NULL DEFAULT FALSE,
    lan_gui_cuoi TIMESTAMPTZ,
    so_loi INTEGER NOT NULL DEFAULT 0,
    thiet_bi VARCHAR(255),
    tao_luc TIMESTAMPTZ NOT NULL DEFAULT NOW())"""


def tao_bang():
    with engine.begin() as c:
        c.execute(text(DDL))


def _duong_khoa() -> Path:
    return Path(os.getenv("VAPID_FILE") or (config.PROJECT_ROOT / "bi_mat" / "vapid_private.pem"))


def vapid():
    """Nạp (hoặc tạo lần đầu) cặp khóa VAPID. Trả về đối tượng py_vapid.Vapid."""
    global _vapid
    with _khoa:
        if _vapid is None:
            from py_vapid import Vapid
            p = _duong_khoa()
            if not p.exists():
                p.parent.mkdir(parents=True, exist_ok=True)
                v = Vapid()
                v.generate_keys()
                v.save_key(str(p))
                try:
                    os.chmod(p, 0o600)
                except OSError:
                    pass
                logbus.ghi("INFO", "day", "tao_khoa_vapid", f"Đã tạo khóa VAPID mới tại {p.name}")
            _vapid = Vapid.from_file(str(p))
    return _vapid


def khoa_cong_khai() -> str:
    """Khóa công khai dạng base64url (điểm EC không nén) cho applicationServerKey phía trình duyệt."""
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    raw = vapid().public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _claims() -> dict:
    lien_he = os.getenv("VAPID_EMAIL") or os.getenv("SMTP_USER")
    sub = f"mailto:{lien_he}" if lien_he else (config.DIA_CHI_CONG_KHAI or "mailto:admin@airhcm.local")
    return {"sub": sub}


def luu_dang_ky(dk: dict, nguong: int, nguoi_dung_id: int | None, thiet_bi: str, cu: str | None = None) -> None:
    ep, keys = dk.get("endpoint"), dk.get("keys") or {}
    if not (isinstance(ep, str) and ep.startswith("https://") and keys.get("p256dh") and keys.get("auth")):
        raise ValueError("Đăng ký thông báo không hợp lệ")
    with engine.begin() as c:
        if cu:
            c.execute(text("DELETE FROM dang_ky_day WHERE endpoint = :e"), {"e": cu})
        c.execute(text("""
            INSERT INTO dang_ky_day (endpoint, p256dh, auth, nguoi_dung_id, nguong_aqi, thiet_bi)
            VALUES (:e, :p, :a, :u, :n, :tb)
            ON CONFLICT (endpoint) DO UPDATE SET p256dh = EXCLUDED.p256dh, auth = EXCLUDED.auth,
                nguong_aqi = EXCLUDED.nguong_aqi, nguoi_dung_id = COALESCE(EXCLUDED.nguoi_dung_id, dang_ky_day.nguoi_dung_id),
                so_loi = 0, dang_vuot = FALSE
        """), {"e": ep, "p": keys["p256dh"], "a": keys["auth"], "u": nguoi_dung_id, "n": nguong, "tb": (thiet_bi or "")[:255]})


def huy_dang_ky(endpoint: str) -> bool:
    with engine.begin() as c:
        return bool(c.execute(text("DELETE FROM dang_ky_day WHERE endpoint = :e"), {"e": endpoint}).rowcount)


def trang_thai(endpoint: str) -> dict | None:
    with engine.connect() as c:
        r = c.execute(text("SELECT nguong_aqi, lan_gui_cuoi FROM dang_ky_day WHERE endpoint = :e"), {"e": endpoint}).fetchone()
    return {"nguong_aqi": r.nguong_aqi, "lan_gui_cuoi": r.lan_gui_cuoi.isoformat() if r.lan_gui_cuoi else None} if r else None


def gui(dong, noi_dung: dict) -> str:
    """Gửi 1 thông báo. Trả 'ok' | 'het_han' (đăng ký không còn, đã xóa) | thông báo lỗi."""
    from pywebpush import WebPushException, webpush
    try:
        webpush(subscription_info={"endpoint": dong.endpoint, "keys": {"p256dh": dong.p256dh, "auth": dong.auth}},
                data=json.dumps(noi_dung, ensure_ascii=False), vapid_private_key=vapid(), vapid_claims=_claims(),
                ttl=6 * 3600, timeout=15)
        return "ok"
    except WebPushException as exc:
        ma = getattr(exc.response, "status_code", None)
        with engine.begin() as c:
            if ma in (404, 410):   # người dùng đã gỡ quyền/gỡ trình duyệt → xóa đăng ký
                c.execute(text("DELETE FROM dang_ky_day WHERE endpoint = :e"), {"e": dong.endpoint})
                return "het_han"
            c.execute(text("UPDATE dang_ky_day SET so_loi = so_loi + 1 WHERE endpoint = :e"), {"e": dong.endpoint})
        return f"Lỗi đẩy {ma}: {str(exc)[:150]}"
    except Exception as exc:  # mạng, khóa...
        return f"{type(exc).__name__}: {exc}"


def gui_thu(endpoint: str) -> str:
    with engine.connect() as c:
        dong = c.execute(text("SELECT endpoint, p256dh, auth FROM dang_ky_day WHERE endpoint = :e"), {"e": endpoint}).fetchone()
    if not dong:
        return "Chưa đăng ký nhận thông báo trên thiết bị này"
    kq = gui(dong, {"tieu_de": "AirHCM – Thông báo thử", "noi_dung": "Thông báo nền hoạt động tốt. Bạn sẽ nhận cảnh báo khi AQI vượt ngưỡng đã chọn.",
                    "tag": "airhcm-thu", "url": "tai-khoan.html"})
    return "Đăng ký trên thiết bị này đã hết hiệu lực, hãy tắt rồi bật lại thông báo" if kq == "het_han" else kq


def _aqi_hien_tai() -> dict | None:
    from services.tong_quan import tong_quan
    h = (tong_quan() or {}).get("hien_tai") or {}
    return h if h.get("aqi") is not None else None


def quet_va_gui() -> dict:
    """Một vòng: so AQI hiện tại với ngưỡng từng đăng ký và gửi thông báo khi cần."""
    kq = {"aqi": None, "da_gui": 0, "het_han": 0, "loi": 0}
    h = _aqi_hien_tai()
    if not h:
        return kq
    aqi = int(h["aqi"])
    kq["aqi"] = aqi
    with engine.begin() as c:
        # Đã xuống dưới ngưỡng − 10 → cho phép báo lại lần sau
        c.execute(text("UPDATE dang_ky_day SET dang_vuot = FALSE WHERE dang_vuot AND :a < nguong_aqi - 10"), {"a": aqi})
        ds = c.execute(text("""
            SELECT endpoint, p256dh, auth FROM dang_ky_day
            WHERE :a >= nguong_aqi AND so_loi < 20
              AND (NOT dang_vuot OR lan_gui_cuoi IS NULL OR lan_gui_cuoi < NOW() - make_interval(secs => :nl))
        """), {"a": aqi, "nl": NHAC_LAI_GIAY}).fetchall()
    if not ds:
        return kq
    noi_dung = {
        "tieu_de": f"AQI TP.HCM {aqi} – {h.get('muc') or ''}".strip(" –"),
        "noi_dung": (f"Chất ô nhiễm chính: {h.get('chat') or '?'}; PM2.5 {h.get('pm25') or '?'} µg/m³. "
                     + (h.get("nhom_nhay_cam") or h.get("nguoi_binh_thuong") or "")).strip()[:230],
        "tag": "airhcm-aqi", "url": "tong-quan.html", "quan_trong": aqi >= 201,
    }
    for d in ds:
        r = gui(d, noi_dung)
        if r == "ok":
            kq["da_gui"] += 1
            with engine.begin() as c:
                c.execute(text("UPDATE dang_ky_day SET dang_vuot = TRUE, lan_gui_cuoi = NOW(), so_loi = 0 WHERE endpoint = :e"),
                          {"e": d.endpoint})
        elif r == "het_han":
            kq["het_han"] += 1
        else:
            kq["loi"] += 1
    logbus.ghi("INFO", "day", "quet_aqi", f"AQI {aqi}: gửi {kq['da_gui']} thông báo đẩy, {kq['het_han']} đăng ký hết hạn, {kq['loi']} lỗi")
    return kq


def _vong_lap():
    time.sleep(90)   # chờ máy chủ khởi động xong
    while True:
        try:
            quet_va_gui()
        except Exception as exc:
            logbus.ghi("ERROR", "day", "loi_vong_lap", f"{type(exc).__name__}: {exc}")
        time.sleep(CHU_KY_GIAY)


def khoi_dong():
    tao_bang()
    try:
        vapid()
    except Exception as exc:
        logbus.ghi("ERROR", "day", "loi_khoa_vapid", f"{type(exc).__name__}: {exc}")
        return
    threading.Thread(target=_vong_lap, daemon=True, name="day_thong_bao").start()
