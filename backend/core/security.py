"""Xác thực: đọc JWT từ cookie HttpOnly (hoặc Bearer), kiểm tra phiên phía máy chủ, kiểm tra quyền admin."""

from core import config  # noqa: F401  (nạp .env và đường dẫn dự án trước)
from auth import decode_access_token
from database import get_db
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
import models
from core.config import COOKIE_NAME
from core import phien


def chuan_hoa_email(email: str) -> str:
    """Chuẩn hóa email Gmail: bỏ dấu chấm trong phần tên, bỏ phần sau dấu +."""
    email = email.strip().lower()
    if "@" not in email:
        return email
    ten, domain = email.split("@", 1)
    if domain in ("gmail.com", "googlemail.com"):
        ten = ten.split("+")[0]        # bỏ phần sau dấu +
        ten = ten.replace(".", "")     # bỏ dấu chấm
        domain = "gmail.com"           # đồng nhất googlemail.com -> gmail.com
    return f"{ten}@{domain}"


def ip_cua(request: Request) -> str:
    """IP người dùng. Sau reverse proxy (Caddy/Nginx), uvicorn chạy với --proxy-headers sẽ tự điền IP thật."""
    return request.client.host if request.client else "?"


def thiet_bi_cua(request: Request) -> str:
    return (request.headers.get("user-agent") or "")[:255]


security_scheme = HTTPBearer(auto_error=False)


def doc_token(request: Request, credentials: HTTPAuthorizationCredentials = None) -> str | None:
    # Ưu tiên cookie HttpOnly (JavaScript phía trình duyệt không đọc được); vẫn nhận Bearer để dùng Swagger/Postman
    return request.cookies.get(COOKIE_NAME) or (credentials.credentials if credentials else None)


def get_current_user(request: Request,
                     credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
                     db: Session = Depends(get_db)):
    token = doc_token(request, credentials)
    if not token:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")
    payload = decode_access_token(token, loai="phien")
    if payload is None:
        raise HTTPException(status_code=401, detail="Phiên đăng nhập không hợp lệ hoặc đã hết hạn")
    user = db.query(models.NguoiDung).filter(models.NguoiDung.email == payload.get("sub")).first()
    if user is None or user.bi_khoa:
        raise HTTPException(status_code=401, detail="Tài khoản không tồn tại hoặc đã bị khóa")
    if not phien.kiem_tra_phien(db, payload.get("sid"), user.id):
        raise HTTPException(status_code=401, detail="Phiên đăng nhập đã kết thúc. Vui lòng đăng nhập lại")
    request.state.sid = payload.get("sid")
    return user


def require_admin(current_user: models.NguoiDung = Depends(get_current_user)):
    if current_user.vai_tro != "admin":
        raise HTTPException(status_code=403, detail="Chỉ Admin mới có quyền thực hiện thao tác này")
    return current_user
