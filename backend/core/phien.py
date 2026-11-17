"""Phiên đăng nhập phía máy chủ + xác thực 2 lớp (TOTP) + mã OTP đặt lại mật khẩu.

Vì sao cần phiên phía máy chủ: JWT thuần không thu hồi được — đăng xuất hay đổi mật khẩu thì token cũ vẫn dùng được
tới khi hết hạn. Ở đây mỗi lần đăng nhập tạo một dòng trong bảng `phien_dang_nhap`; cookie chứa JWT có "sid".
Mỗi yêu cầu đều kiểm tra phiên còn hiệu lực, chưa bị thu hồi và chưa quá thời gian không hoạt động.

- Đăng xuất → thu hồi phiên hiện tại. Đổi/đặt lại mật khẩu, tắt 2FA → thu hồi mọi phiên khác.
- Người dùng xem và đăng xuất từng thiết bị ở trang Tài khoản (tai-khoan.html).
- Bí mật TOTP được mã hóa (Fernet) trước khi lưu; mã dự phòng và mã OTP chỉ lưu dạng băm SHA-256.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from core import config  # noqa: F401  (nạp .env)

# ---- Cấu hình thời hạn (giây) ----
HAN_TUYET_DOI = int(os.getenv("COOKIE_MAX_AGE", str(8 * 3600)))                       # phiên thường: 8 giờ
HAN_KHONG_HOAT_DONG = int(os.getenv("PHIEN_KHONG_HOAT_DONG_PHUT", "120")) * 60          # tự đăng xuất khi bỏ quên 2 giờ
HAN_GHI_NHO = int(os.getenv("PHIEN_GHI_NHO_NGAY", "30")) * 86400                        # "Ghi nhớ đăng nhập": 30 ngày
HAN_GHI_NHO_KHONG_HOAT_DONG = 7 * 86400
TOI_DA_PHIEN = 10              # mỗi tài khoản tối đa 10 phiên đang mở; vượt thì đóng phiên cũ nhất
CAP_NHAT_LAN_CUOI_SAU = 60     # chỉ ghi lan_cuoi tối đa 1 lần/phút để giảm ghi CSDL

DDL = [
    # Bảng OTP đặt lại mật khẩu (trước đây chỉ có trong backup.sql → cài máy mới bị thiếu)
    """CREATE TABLE IF NOT EXISTS otp_reset (
        id SERIAL PRIMARY KEY,
        email VARCHAR(255) NOT NULL,
        ma_otp VARCHAR(6) NOT NULL DEFAULT '',
        het_han TIMESTAMP NOT NULL,
        da_dung BOOLEAN DEFAULT FALSE)""",
    "ALTER TABLE otp_reset ADD COLUMN IF NOT EXISTS ma_hash CHAR(64)",
    "ALTER TABLE otp_reset ADD COLUMN IF NOT EXISTS so_lan_thu INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE otp_reset ADD COLUMN IF NOT EXISTS ip VARCHAR(64)",
    "CREATE INDEX IF NOT EXISTS ix_otp_reset_email ON otp_reset (email)",
    # Cột bảo mật cho tài khoản
    "ALTER TABLE nguoi_dung ADD COLUMN IF NOT EXISTS totp_bat BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE nguoi_dung ADD COLUMN IF NOT EXISTS totp_bi_mat TEXT",
    "ALTER TABLE nguoi_dung ADD COLUMN IF NOT EXISTS totp_buoc_cuoi BIGINT",
    "ALTER TABLE nguoi_dung ADD COLUMN IF NOT EXISTS ma_du_phong TEXT",
    "ALTER TABLE nguoi_dung ADD COLUMN IF NOT EXISTS mat_khau_doi_luc TIMESTAMPTZ",
    "ALTER TABLE nguoi_dung ADD COLUMN IF NOT EXISTS dang_nhap_cuoi TIMESTAMPTZ",
    "ALTER TABLE nguoi_dung ADD COLUMN IF NOT EXISTS bi_khoa BOOLEAN NOT NULL DEFAULT FALSE",
    # Phiên đăng nhập
    """CREATE TABLE IF NOT EXISTS phien_dang_nhap (
        id SERIAL PRIMARY KEY,
        sid_hash CHAR(64) UNIQUE NOT NULL,
        nguoi_dung_id INTEGER NOT NULL REFERENCES nguoi_dung(id) ON DELETE CASCADE,
        tao_luc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        lan_cuoi TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        het_han TIMESTAMPTZ NOT NULL,
        khong_hoat_dong_giay INTEGER NOT NULL,
        ip VARCHAR(64),
        thiet_bi VARCHAR(255),
        hai_lop BOOLEAN NOT NULL DEFAULT FALSE,
        thu_hoi_luc TIMESTAMPTZ,
        ly_do_thu_hoi VARCHAR(50))""",
    "CREATE INDEX IF NOT EXISTS ix_phien_nguoi_dung ON phien_dang_nhap (nguoi_dung_id) WHERE thu_hoi_luc IS NULL",
    # Đăng nhập bằng Google / Facebook / Zalo (core/oauth.py)
    "ALTER TABLE nguoi_dung ADD COLUMN IF NOT EXISTS co_mat_khau BOOLEAN NOT NULL DEFAULT TRUE",
    """CREATE TABLE IF NOT EXISTS lien_ket_mxh (
        id SERIAL PRIMARY KEY,
        nguoi_dung_id INTEGER NOT NULL REFERENCES nguoi_dung(id) ON DELETE CASCADE,
        nha_cung_cap VARCHAR(20) NOT NULL,
        ma_ngoai VARCHAR(255) NOT NULL,
        email VARCHAR(255),
        ho_ten VARCHAR(255),
        tao_luc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        dang_nhap_cuoi TIMESTAMPTZ,
        UNIQUE (nha_cung_cap, ma_ngoai),
        UNIQUE (nguoi_dung_id, nha_cung_cap))""",
]


def tao_bang(engine) -> None:
    """Tạo/nâng cấp các bảng bảo mật. Chạy được nhiều lần (IF NOT EXISTS). Gọi ngay khi máy chủ khởi động."""
    with engine.begin() as conn:
        for cau in DDL:
            conn.execute(text(cau))


def _bam(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _bay_gio() -> datetime:
    return datetime.now(timezone.utc)


# =================================================================== PHIÊN ĐĂNG NHẬP
def tao_phien(db, nguoi_dung_id: int, ip: str | None, thiet_bi: str | None, ghi_nho: bool = False,
              hai_lop: bool = False) -> tuple[str, int]:
    """Tạo phiên mới, trả về (sid, số giây hiệu lực tuyệt đối) để đặt vào JWT/cookie."""
    sid = secrets.token_urlsafe(32)
    han = HAN_GHI_NHO if ghi_nho else HAN_TUYET_DOI
    roi = HAN_GHI_NHO_KHONG_HOAT_DONG if ghi_nho else HAN_KHONG_HOAT_DONG
    db.execute(text("""
        INSERT INTO phien_dang_nhap (sid_hash, nguoi_dung_id, het_han, khong_hoat_dong_giay, ip, thiet_bi, hai_lop)
        VALUES (:h, :u, :hh, :roi, :ip, :tb, :hl)
    """), {"h": _bam(sid), "u": nguoi_dung_id, "hh": _bay_gio() + timedelta(seconds=han), "roi": roi,
           "ip": (ip or "")[:64], "tb": (thiet_bi or "")[:255], "hl": hai_lop})
    # Giới hạn số phiên đang mở: đóng các phiên cũ nhất vượt quá TOI_DA_PHIEN
    db.execute(text("""
        UPDATE phien_dang_nhap SET thu_hoi_luc = NOW(), ly_do_thu_hoi = 'vuot_so_phien'
        WHERE id IN (SELECT id FROM phien_dang_nhap WHERE nguoi_dung_id = :u AND thu_hoi_luc IS NULL
                     ORDER BY lan_cuoi DESC OFFSET :n)
    """), {"u": nguoi_dung_id, "n": TOI_DA_PHIEN})
    db.execute(text("UPDATE nguoi_dung SET dang_nhap_cuoi = NOW() WHERE id = :u"), {"u": nguoi_dung_id})
    db.commit()
    return sid, han


def kiem_tra_phien(db, sid: str, nguoi_dung_id: int) -> bool:
    """Phiên còn hiệu lực? (đúng chủ, chưa thu hồi, chưa hết hạn, chưa quá thời gian không hoạt động).
    Hợp lệ thì gia hạn mốc hoạt động cuối (tối đa 1 lần/phút)."""
    if not sid:
        return False
    r = db.execute(text("""
        SELECT id, nguoi_dung_id, het_han, lan_cuoi, khong_hoat_dong_giay, thu_hoi_luc
        FROM phien_dang_nhap WHERE sid_hash = :h
    """), {"h": _bam(sid)}).fetchone()
    now = _bay_gio()
    if r is None or r.nguoi_dung_id != nguoi_dung_id or r.thu_hoi_luc is not None:
        return False
    if r.het_han <= now:
        return False
    if r.lan_cuoi + timedelta(seconds=r.khong_hoat_dong_giay) <= now:
        db.execute(text("UPDATE phien_dang_nhap SET thu_hoi_luc = NOW(), ly_do_thu_hoi = 'khong_hoat_dong' WHERE id = :i"),
                   {"i": r.id})
        db.commit()
        return False
    if (now - r.lan_cuoi).total_seconds() > CAP_NHAT_LAN_CUOI_SAU:
        db.execute(text("UPDATE phien_dang_nhap SET lan_cuoi = NOW() WHERE id = :i"), {"i": r.id})
        db.commit()
    return True


def thu_hoi_phien(db, sid: str, ly_do: str = "dang_xuat") -> None:
    if sid:
        db.execute(text("UPDATE phien_dang_nhap SET thu_hoi_luc = NOW(), ly_do_thu_hoi = :l "
                        "WHERE sid_hash = :h AND thu_hoi_luc IS NULL"), {"h": _bam(sid), "l": ly_do})
        db.commit()


def thu_hoi_tat_ca(db, nguoi_dung_id: int, tru_sid: str | None = None, ly_do: str = "dang_xuat_tat_ca") -> int:
    """Thu hồi mọi phiên của tài khoản (trừ phiên hiện tại nếu truyền tru_sid). Trả về số phiên bị đóng."""
    r = db.execute(text("""
        UPDATE phien_dang_nhap SET thu_hoi_luc = NOW(), ly_do_thu_hoi = :l
        WHERE nguoi_dung_id = :u AND thu_hoi_luc IS NULL AND sid_hash <> :tru
    """), {"u": nguoi_dung_id, "l": ly_do, "tru": _bam(tru_sid) if tru_sid else ""})
    db.commit()
    return r.rowcount or 0


def ds_phien(db, nguoi_dung_id: int, sid_hien_tai: str | None) -> list[dict]:
    hien = _bam(sid_hien_tai) if sid_hien_tai else ""
    rows = db.execute(text("""
        SELECT id, sid_hash, tao_luc, lan_cuoi, het_han, ip, thiet_bi, hai_lop FROM phien_dang_nhap
        WHERE nguoi_dung_id = :u AND thu_hoi_luc IS NULL AND het_han > NOW()
          AND lan_cuoi + make_interval(secs => khong_hoat_dong_giay) > NOW()
        ORDER BY lan_cuoi DESC
    """), {"u": nguoi_dung_id}).fetchall()
    return [{"id": r.id, "tao_luc": r.tao_luc.isoformat(), "lan_cuoi": r.lan_cuoi.isoformat(),
             "het_han": r.het_han.isoformat(), "ip": r.ip, "thiet_bi": r.thiet_bi, "hai_lop": r.hai_lop,
             "hien_tai": r.sid_hash == hien} for r in rows]


def thu_hoi_theo_id(db, nguoi_dung_id: int, phien_id: int) -> bool:
    r = db.execute(text("""
        UPDATE phien_dang_nhap SET thu_hoi_luc = NOW(), ly_do_thu_hoi = 'nguoi_dung_thu_hoi'
        WHERE id = :i AND nguoi_dung_id = :u AND thu_hoi_luc IS NULL
    """), {"i": phien_id, "u": nguoi_dung_id})
    db.commit()
    return bool(r.rowcount)


# =================================================================== XÁC THỰC 2 LỚP (TOTP, RFC 6238)
def _fernet():
    from cryptography.fernet import Fernet
    nguon = os.getenv("TOTP_ENC_KEY") or ("airhcm-totp:" + os.getenv("JWT_SECRET_KEY", ""))
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(nguon.encode()).digest()))


def ma_hoa_bi_mat(bi_mat: str) -> str:
    return _fernet().encrypt(bi_mat.encode()).decode()


def giai_ma_bi_mat(chuoi: str | None) -> str | None:
    if not chuoi:
        return None
    try:
        return _fernet().decrypt(chuoi.encode()).decode()
    except Exception:
        return None


def tao_bi_mat_totp() -> str:
    import pyotp
    return pyotp.random_base32()


def uri_totp(bi_mat: str, email: str) -> str:
    import pyotp
    return pyotp.TOTP(bi_mat).provisioning_uri(name=email, issuer_name="AirHCM")


def qr_svg(noi_dung: str) -> str:
    """Mã QR dạng SVG (không cần thư viện ảnh) để quét bằng Google Authenticator / Microsoft Authenticator."""
    import io
    import qrcode
    import qrcode.image.svg
    buf = io.BytesIO()
    qrcode.make(noi_dung, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2).save(buf)
    return buf.getvalue().decode()


def kiem_tra_totp(bi_mat: str, ma: str, buoc_cuoi: int | None) -> int | None:
    """Kiểm tra mã 6 số (cho lệch ±30 giây). Trả về bước thời gian đã dùng (để chống dùng lại mã), None nếu sai
    hoặc mã đã được dùng trước đó."""
    import pyotp
    ma = (ma or "").strip().replace(" ", "")
    if not (ma.isdigit() and len(ma) == 6):
        return None
    t = pyotp.TOTP(bi_mat)
    hien_tai = int(_bay_gio().timestamp()) // t.interval
    for buoc in (hien_tai, hien_tai - 1, hien_tai + 1):
        if hmac.compare_digest(t.generate_otp(buoc), ma):
            if buoc_cuoi is not None and buoc <= buoc_cuoi:
                return None          # chống phát lại (replay) mã vừa dùng
            return buoc
    return None


def tao_ma_du_phong(so_luong: int = 8) -> tuple[list[str], str]:
    """Sinh mã dự phòng (dùng khi mất điện thoại). Trả về (danh sách mã hiển thị 1 lần, JSON băm để lưu)."""
    bang = "abcdefghjkmnpqrstuvwxyz23456789"
    ds = ["".join(secrets.choice(bang) for _ in range(4)) + "-" + "".join(secrets.choice(bang) for _ in range(4))
          for _ in range(so_luong)]
    return ds, json.dumps([_bam(m) for m in ds])


def dung_ma_du_phong(json_bam: str | None, ma: str) -> str | None:
    """Mã dự phòng đúng → trả về JSON mới (đã bỏ mã vừa dùng); sai → None."""
    try:
        ds = json.loads(json_bam or "[]")
    except ValueError:
        return None
    h = _bam((ma or "").strip().lower())
    for x in ds:
        if hmac.compare_digest(x, h):
            ds.remove(x)
            return json.dumps(ds)
    return None


# =================================================================== OTP ĐẶT LẠI MẬT KHẨU
OTP_HIEU_LUC_PHUT = 10
OTP_SO_LAN_THU = 5


def tao_otp(db, email: str, ip: str | None) -> str:
    """Sinh OTP 6 số; chỉ lưu bản băm. Các mã cũ chưa dùng của email này bị vô hiệu."""
    ma = "".join(secrets.choice("0123456789") for _ in range(6))
    db.execute(text("UPDATE otp_reset SET da_dung = TRUE WHERE email = :e AND da_dung = FALSE"), {"e": email})
    db.execute(text("""
        INSERT INTO otp_reset (email, ma_otp, ma_hash, het_han, ip) VALUES (:e, '', :h, :hh, :ip)
    """), {"e": email, "h": _bam(email + ":" + ma), "hh": datetime.now() + timedelta(minutes=OTP_HIEU_LUC_PHUT),
           "ip": (ip or "")[:64]})
    db.commit()
    return ma


def otp_gan_day(db, email: str, giay: int = 60) -> bool:
    """Đã gửi OTP cho email này trong `giay` giây gần đây chưa (chống spam email)."""
    return db.execute(text("""
        SELECT 1 FROM otp_reset WHERE email = :e AND het_han > :moc LIMIT 1
    """), {"e": email, "moc": datetime.now() + timedelta(minutes=OTP_HIEU_LUC_PHUT) - timedelta(seconds=giay)}).fetchone() is not None


def xac_nhan_otp(db, email: str, ma: str) -> bool:
    """Đúng mã → đánh dấu đã dùng, trả True. Sai → tăng số lần thử; quá OTP_SO_LAN_THU lần thì hủy mã."""
    r = db.execute(text("""
        SELECT id, ma_hash, so_lan_thu FROM otp_reset
        WHERE email = :e AND da_dung = FALSE AND het_han > NOW() ORDER BY id DESC LIMIT 1
    """), {"e": email}).fetchone()
    if r is None or not r.ma_hash:
        return False
    if hmac.compare_digest(r.ma_hash, _bam(email + ":" + (ma or "").strip())):
        db.execute(text("UPDATE otp_reset SET da_dung = TRUE WHERE id = :i"), {"i": r.id})
        db.commit()
        return True
    db.execute(text("""
        UPDATE otp_reset SET so_lan_thu = so_lan_thu + 1, da_dung = (so_lan_thu + 1 >= :n) WHERE id = :i
    """), {"i": r.id, "n": OTP_SO_LAN_THU})
    db.commit()
    return False
