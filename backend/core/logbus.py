"""Nhật ký hệ thống tập trung: mọi thành phần (đăng nhập, API lỗi, gửi mail, nạp dữ liệu,
sự kiện CDC...) ghi về MỘT bảng `nhat_ky_he_thong` để quản trị viên tra cứu trên trang Nhật ký.

Nguyên tắc: ghi nhật ký KHÔNG BAO GIỜ làm hỏng chức năng chính (lỗi ghi log chỉ in ra console).
"""

from core import config  # noqa: F401  (nạp .env và đường dẫn dự án trước)
import json
from datetime import datetime
from sqlalchemy import text
from database import engine

MUC = ("INFO", "WARN", "ERROR")
_san_sang = False


def tao_bang_nhat_ky(giu_ngay: int = 90):
    """Tạo bảng nếu chưa có và xóa nhật ký cũ hơn `giu_ngay` ngày."""
    global _san_sang
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS nhat_ky_he_thong (
                    id BIGSERIAL PRIMARY KEY,
                    thoi_gian TIMESTAMP NOT NULL DEFAULT NOW(),
                    muc VARCHAR(8) NOT NULL,
                    nguon VARCHAR(30) NOT NULL,
                    su_kien VARCHAR(60) NOT NULL,
                    noi_dung TEXT,
                    nguoi_dung VARCHAR(255),
                    chi_tiet JSONB
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_nhat_ky_tg ON nhat_ky_he_thong (thoi_gian DESC)"))
            conn.execute(text("DELETE FROM nhat_ky_he_thong WHERE thoi_gian < NOW() - (:n * INTERVAL '1 day')"), {"n": giu_ngay})
        _san_sang = True
    except Exception as exc:
        print(f"[NHAT KY] Không tạo được bảng nhật ký: {exc}")


def ghi(muc: str, nguon: str, su_kien: str, noi_dung: str = "", nguoi_dung: str = None, **chi_tiet):
    """Ghi 1 dòng nhật ký. muc: INFO | WARN | ERROR."""
    muc = muc if muc in MUC else "INFO"
    print(f"[{datetime.now():%H:%M:%S}] [{muc}] [{nguon}] {su_kien}: {noi_dung}")
    if not _san_sang:
        return
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO nhat_ky_he_thong (muc, nguon, su_kien, noi_dung, nguoi_dung, chi_tiet)
                VALUES (:muc, :nguon, :sk, :nd, :u, CAST(:ct AS JSONB))
            """), {"muc": muc, "nguon": nguon[:30], "sk": su_kien[:60], "nd": (noi_dung or "")[:2000],
                   "u": nguoi_dung, "ct": json.dumps(chi_tiet, ensure_ascii=False, default=str) if chi_tiet else None})
    except Exception as exc:
        print(f"[NHAT KY] Ghi nhật ký thất bại: {exc}")
