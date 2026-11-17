"""Xử lý xác thực: băm mật khẩu (Argon2id), tạo/kiểm tra JWT token.

- Mật khẩu băm bằng Argon2id (khuyến nghị OWASP). Hash bcrypt cũ vẫn đăng nhập được và được băm lại
  bằng Argon2id ngay lần đăng nhập thành công kế tiếp (can_bam_lai).
- JWT ký HS256, có iat, exp, jti, iss; khi gắn với phiên đăng nhập thì có thêm "sid" để máy chủ thu hồi được.
"""

import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from jose import JWTError, jwt
from passlib.context import CryptContext

# Tìm file .env ở thư mục gốc dự án (lùi lên từ backend/)
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)

# Không có khóa dự phòng trong mã: thiếu khóa thì dừng ngay, tránh chạy với khóa công khai.
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
if len(SECRET_KEY) < 32:
    raise RuntimeError(
        "Thiếu JWT_SECRET_KEY (cần >= 32 ký tự) trong file .env. Tạo khóa bằng: "
        'python -c "import secrets; print(secrets.token_urlsafe(48))"'
    )
ALGORITHM = "HS256"
ISSUER = "airhcm"
# Cùng một nguồn với thời hạn cookie (core/config.py): mặc định 8 giờ = 28800 giây
ACCESS_TOKEN_EXPIRE_SECONDS = int(os.getenv("COOKIE_MAX_AGE", str(8 * 3600)))

# Argon2id là thuật toán chính; bcrypt chỉ còn để kiểm tra hash cũ (deprecated="auto" → cần băm lại)
pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")

# Hash giả để so sánh khi email không tồn tại: thời gian phản hồi như nhau, không lộ email nào đã đăng ký
_HASH_GIA = pwd_context.hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except (ValueError, TypeError):
        return False


def verify_password_gia(plain_password: str) -> bool:
    """Gọi khi không tìm thấy người dùng: tốn thời gian như một lần kiểm tra thật, luôn trả về False."""
    pwd_context.verify(plain_password, _HASH_GIA)
    return False


def can_bam_lai(hashed_password: str) -> bool:
    """True nếu hash dùng thuật toán/tham số cũ (vd. bcrypt) và nên băm lại bằng Argon2id."""
    try:
        return pwd_context.needs_update(hashed_password)
    except (ValueError, TypeError):
        return False


def _bay_gio() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(data: dict, het_han_giay: int | None = None):
    now = _bay_gio()
    to_encode = data.copy()
    to_encode.update({
        "iat": now,
        "exp": now + timedelta(seconds=het_han_giay or ACCESS_TOKEN_EXPIRE_SECONDS),
        "jti": secrets.token_urlsafe(12),
        "iss": ISSUER,
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str, loai: str | None = None):
    """Giải mã token; trả None nếu sai chữ ký, hết hạn, sai nơi phát hành hoặc sai loại (typ)."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"require_exp": True})
    except JWTError:
        return None
    if payload.get("iss", ISSUER) != ISSUER:
        return None
    if loai is not None and payload.get("typ") != loai:
        return None
    return payload
