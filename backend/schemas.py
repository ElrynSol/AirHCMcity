"""Pydantic schemas - định dạng dữ liệu vào/ra API."""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class UserRegister(BaseModel):
    ho_ten: str = Field(min_length=2, max_length=100)
    email: EmailStr
    mat_khau: str = Field(max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    mat_khau: str = Field(max_length=128)
    ghi_nho: bool = False          # "Ghi nhớ đăng nhập" trên thiết bị cá nhân (phiên 30 ngày)


class UserOut(BaseModel):
    id: int
    ho_ten: str
    email: str
    vai_tro: str
    totp_bat: bool = False
    co_mat_khau: bool = True

    class Config:
        from_attributes = True


class DangNhapOut(BaseModel):
    """Kết quả đăng nhập. Token KHÔNG trả trong JSON (chỉ nằm trong cookie HttpOnly) để mã độc XSS không lấy được.
    Nếu tài khoản bật xác thực 2 lớp: can_2fa = True, kèm ma_tam (hiệu lực 5 phút) để gửi cùng mã 6 số."""
    user: Optional[UserOut] = None
    can_2fa: bool = False
    ma_tam: Optional[str] = None


class TramCreate(BaseModel):
    ma_tram: str
    ten_tram: str
    vi_do: float
    kinh_do: float
    trang_thai: Optional[str] = "Hoat Dong"


class TramUpdate(BaseModel):
    ma_tram: Optional[str] = None
    ten_tram: Optional[str] = None
    vi_do: Optional[float] = None
    kinh_do: Optional[float] = None
    trang_thai: Optional[str] = None


class TramOut(BaseModel):
    id: int
    ma_tram: Optional[str] = None
    ten_tram: str
    vi_do: Optional[float] = None
    kinh_do: Optional[float] = None
    trang_thai: str