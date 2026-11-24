"""Xác thực chuẩn doanh nghiệp: đăng ký, đăng nhập (cookie HttpOnly + phiên phía máy chủ), xác thực 2 lớp TOTP,
quản lý phiên/thiết bị, đổi mật khẩu, quên mật khẩu bằng OTP email.

Nguyên tắc bảo mật (OWASP ASVS mức 2):
- Mật khẩu băm Argon2id; chính sách độ mạnh (core/mat_khau.py); hash bcrypt cũ tự nâng cấp khi đăng nhập.
- Token chỉ nằm trong cookie HttpOnly + SameSite=Strict (+ Secure khi HTTPS); không trả token trong JSON.
- Phiên phía máy chủ: đăng xuất/đổi mật khẩu thu hồi được ngay; tự hết hạn khi không hoạt động.
- Chống dò mật khẩu: khóa theo (email, IP) và theo email trên mọi IP; giới hạn tần suất đăng ký/OTP/2FA.
- Không lộ email nào đã đăng ký ở chức năng quên mật khẩu; thời gian phản hồi đăng nhập như nhau dù email sai.
- OTP 6 số chỉ lưu bản băm, hiệu lực 10 phút, tự hủy sau 5 lần nhập sai.
- Mọi sự kiện bảo mật ghi vào nhật ký tập trung (logbus).
"""

import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from core import config  # noqa: F401  (nạp .env và đường dẫn dự án trước)
import models
import schemas
from auth import (can_bam_lai, create_access_token, decode_access_token, hash_password, verify_password,
                  verify_password_gia)
from core import logbus, phien, ratelimit
from core.config import COOKIE_NAME
from core.mailer import gui_email_otp
from core.mat_khau import kiem_tra_mat_khau
from core.security import chuan_hoa_email, doc_token, get_current_user, ip_cua, thiet_bi_cua
from database import get_db

router = APIRouter()

HAN_MA_TAM_2FA = 300   # giây: thời gian nhập mã 6 số sau khi đúng mật khẩu


def _bat(ten: str, mac_dinh: str = "0") -> bool:
    return os.getenv(ten, mac_dinh).strip().lower() in ("1", "true", "yes", "on")


def _cho(giay: int) -> str:
    return f"{(giay + 59) // 60} phút" if giay >= 60 else f"{giay} giây"


def _https(request: Request) -> bool:
    qua_proxy = bool(request.client and request.client.host in ("127.0.0.1", "::1"))
    xfp = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    return request.url.scheme == "https" or (qua_proxy and xfp == "https") or _bat("COOKIE_SECURE")


def _dat_cookie(request: Request, response: Response, token: str, han: int, ghi_nho: bool) -> None:
    # Không "ghi nhớ" → cookie phiên trình duyệt (mất khi đóng trình duyệt); có "ghi nhớ" → cookie lưu tới hết hạn phiên
    response.set_cookie(key=COOKIE_NAME, value=token, max_age=han if ghi_nho else None, path="/",
                        httponly=True, samesite="strict", secure=_https(request))


def _xoa_cookie(request: Request, response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="strict", secure=_https(request))


def _mo_phien(db, user, request: Request, response: Response, ghi_nho: bool, hai_lop: bool):
    sid, han = phien.tao_phien(db, user.id, ip_cua(request), thiet_bi_cua(request), ghi_nho=ghi_nho, hai_lop=hai_lop)
    token = create_access_token({"sub": user.email, "sid": sid, "typ": "phien"}, het_han_giay=han)
    _dat_cookie(request, response, token, han, ghi_nho)
    logbus.ghi("INFO", "auth", "dang_nhap", f"Đăng nhập thành công ({user.vai_tro}{', 2 lớp' if hai_lop else ''})",
               nguoi_dung=user.email, ip=ip_cua(request))
    return {"user": user, "can_2fa": False}


def _sid_hien_tai(request: Request) -> str | None:
    t = doc_token(request)
    p = decode_access_token(t, loai="phien") if t else None
    return p.get("sid") if p else None


# =================================================================== ĐĂNG KÝ
@router.post("/api/v1/auth/register", response_model=schemas.UserOut)
def register(user: schemas.UserRegister, request: Request, db: Session = Depends(get_db)):
    if not _bat("CHO_PHEP_DANG_KY", "1"):
        raise HTTPException(status_code=403, detail="Hệ thống đang tạm khóa đăng ký tài khoản mới")
    ip = ip_cua(request)
    cho = ratelimit.vuot_gioi_han("dang_ky", ip, toi_da=5, cua_so_giay=3600)
    if cho:
        raise HTTPException(status_code=429, detail=f"Đăng ký quá nhiều lần. Vui lòng thử lại sau {_cho(cho)}")

    email_chuan = chuan_hoa_email(user.email)
    ho_ten = " ".join(user.ho_ten.split())
    loi = kiem_tra_mat_khau(user.mat_khau, email_chuan, ho_ten)
    if loi:
        raise HTTPException(status_code=400, detail=loi)
    if db.query(models.NguoiDung).filter(models.NguoiDung.email == email_chuan).first():
        raise HTTPException(status_code=400, detail="Email đã được đăng ký")

    # Quyền admin: email trong ADMIN_EMAILS (.env). Chưa cấu hình ADMIN_EMAILS thì tài khoản đầu tiên là admin
    # (chỉ nên dùng khi cài đặt lần đầu trên máy cá nhân; máy chủ công khai PHẢI đặt ADMIN_EMAILS).
    ds_admin = {chuan_hoa_email(e) for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()}
    if ds_admin:
        vai_tro = "admin" if email_chuan in ds_admin else "viewer"
    else:
        vai_tro = "admin" if db.query(models.NguoiDung).count() == 0 else "viewer"

    new_user = models.NguoiDung(ho_ten=ho_ten, email=email_chuan, mat_khau_hash=hash_password(user.mat_khau),
                                vai_tro=vai_tro, mat_khau_doi_luc=datetime.now(timezone.utc))
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    logbus.ghi("INFO", "auth", "dang_ky", f"Tài khoản mới ({vai_tro})", nguoi_dung=email_chuan, ip=ip)
    return new_user


# =================================================================== ĐĂNG NHẬP
@router.post("/api/v1/auth/login", response_model=schemas.DangNhapOut)
def login(credentials: schemas.UserLogin, request: Request, response: Response, db: Session = Depends(get_db)):
    email_chuan = chuan_hoa_email(credentials.email)
    ip = ip_cua(request)
    cho = ratelimit.con_lai_giay(email_chuan, ip)
    if cho:
        logbus.ghi("WARN", "auth", "dang_nhap_bi_khoa", "Tạm khóa do sai mật khẩu nhiều lần", nguoi_dung=email_chuan, ip=ip)
        raise HTTPException(status_code=429, detail=f"Sai mật khẩu quá nhiều lần. Vui lòng thử lại sau {_cho(cho)}.")

    user = db.query(models.NguoiDung).filter(models.NguoiDung.email == email_chuan).first()
    dung = verify_password(credentials.mat_khau, user.mat_khau_hash) if user else verify_password_gia(credentials.mat_khau)
    if not dung:
        ratelimit.ghi_that_bai(email_chuan, ip)
        logbus.ghi("WARN", "auth", "dang_nhap_that_bai", "Sai email hoặc mật khẩu", nguoi_dung=email_chuan, ip=ip)
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng")
    ratelimit.xoa(email_chuan, ip)

    if user.bi_khoa:
        logbus.ghi("WARN", "auth", "dang_nhap_tk_bi_khoa", "Tài khoản đã bị khóa", nguoi_dung=email_chuan, ip=ip)
        raise HTTPException(status_code=403, detail="Tài khoản đã bị quản trị viên khóa")
    if can_bam_lai(user.mat_khau_hash):          # bcrypt cũ → Argon2id
        user.mat_khau_hash = hash_password(credentials.mat_khau)
        db.commit()

    if user.totp_bat:
        ma_tam = create_access_token({"sub": user.email, "typ": "2fa", "ghi_nho": credentials.ghi_nho},
                                     het_han_giay=HAN_MA_TAM_2FA)
        return {"user": None, "can_2fa": True, "ma_tam": ma_tam}
    return _mo_phien(db, user, request, response, credentials.ghi_nho, hai_lop=False)


class MaHaiLop(BaseModel):
    ma_tam: str = Field(max_length=2000)
    ma: str = Field(min_length=6, max_length=20)   # 6 số TOTP hoặc mã dự phòng dạng xxxx-xxxx


@router.post("/api/v1/auth/2fa/dang-nhap", response_model=schemas.DangNhapOut)
def dang_nhap_2fa(body: MaHaiLop, request: Request, response: Response, db: Session = Depends(get_db)):
    p = decode_access_token(body.ma_tam, loai="2fa")
    if not p:
        raise HTTPException(status_code=401, detail="Đã quá thời gian nhập mã. Vui lòng đăng nhập lại")
    email = p.get("sub")
    cho = ratelimit.vuot_gioi_han("2fa", email, toi_da=5, cua_so_giay=300)
    if cho:
        raise HTTPException(status_code=429, detail=f"Nhập sai mã quá nhiều lần. Vui lòng thử lại sau {_cho(cho)}")
    user = db.query(models.NguoiDung).filter(models.NguoiDung.email == email).first()
    if not user or not user.totp_bat or user.bi_khoa:
        raise HTTPException(status_code=401, detail="Không xác thực được tài khoản")

    bi_mat = phien.giai_ma_bi_mat(user.totp_bi_mat)
    buoc = phien.kiem_tra_totp(bi_mat, body.ma, user.totp_buoc_cuoi) if bi_mat else None
    if buoc is not None:
        user.totp_buoc_cuoi = buoc
    else:
        con_lai = phien.dung_ma_du_phong(user.ma_du_phong, body.ma)
        if con_lai is None:
            logbus.ghi("WARN", "auth", "sai_ma_2fa", "Sai mã xác thực 2 lớp", nguoi_dung=email, ip=ip_cua(request))
            raise HTTPException(status_code=401, detail="Mã xác thực không đúng")
        user.ma_du_phong = con_lai
        logbus.ghi("WARN", "auth", "dung_ma_du_phong", "Đăng nhập bằng mã dự phòng", nguoi_dung=email, ip=ip_cua(request))
    db.commit()
    return _mo_phien(db, user, request, response, bool(p.get("ghi_nho")), hai_lop=True)


@router.post("/api/v1/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    sid = _sid_hien_tai(request)
    if sid:
        phien.thu_hoi_phien(db, sid, "dang_xuat")
    _xoa_cookie(request, response)
    logbus.ghi("INFO", "auth", "dang_xuat", "Đăng xuất", ip=ip_cua(request))
    return {"message": "Đã đăng xuất"}


@router.get("/api/v1/auth/me", response_model=schemas.UserOut)
def get_me(current_user: models.NguoiDung = Depends(get_current_user)):
    return current_user


# =================================================================== PHIÊN / THIẾT BỊ
@router.get("/api/v1/auth/phien")
def ds_phien(request: Request, user: models.NguoiDung = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"phien": phien.ds_phien(db, user.id, getattr(request.state, "sid", None)),
            "dang_nhap_cuoi": user.dang_nhap_cuoi.isoformat() if user.dang_nhap_cuoi else None,
            "mat_khau_doi_luc": user.mat_khau_doi_luc.isoformat() if user.mat_khau_doi_luc else None,
            "totp_bat": bool(user.totp_bat),
            "so_ma_du_phong": len(json.loads(user.ma_du_phong or "[]")) if user.totp_bat else 0}


@router.delete("/api/v1/auth/phien/{phien_id}")
def thu_hoi_phien(phien_id: int, request: Request, user: models.NguoiDung = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    if not phien.thu_hoi_theo_id(db, user.id, phien_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên")
    logbus.ghi("INFO", "auth", "thu_hoi_phien", f"Đăng xuất một thiết bị (phiên {phien_id})", nguoi_dung=user.email,
               ip=ip_cua(request))
    return {"message": "Đã đăng xuất thiết bị"}


@router.post("/api/v1/auth/dang-xuat-tat-ca")
def dang_xuat_tat_ca(request: Request, response: Response, user: models.NguoiDung = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    n = phien.thu_hoi_tat_ca(db, user.id, ly_do="dang_xuat_tat_ca")
    _xoa_cookie(request, response)
    logbus.ghi("WARN", "auth", "dang_xuat_tat_ca", f"Đăng xuất khỏi mọi thiết bị ({n} phiên)", nguoi_dung=user.email,
               ip=ip_cua(request))
    return {"message": f"Đã đăng xuất {n} phiên trên mọi thiết bị"}


# =================================================================== ĐỔI MẬT KHẨU
class DoiMatKhau(BaseModel):
    mat_khau_cu: str = Field("", max_length=128)   # bỏ trống khi tài khoản mạng xã hội đặt mật khẩu lần đầu
    mat_khau_moi: str = Field(max_length=128)


def _xac_nhan_mat_khau(user, mat_khau: str, request: Request) -> None:
    """Xác nhận lại mật khẩu trước thao tác nhạy cảm (đổi mật khẩu, bật/tắt 2 lớp)."""
    if not user.co_mat_khau:
        raise HTTPException(status_code=400, detail="Tài khoản đăng nhập bằng Google/Facebook/Zalo chưa có mật khẩu. Hãy đặt mật khẩu ở mục Đổi mật khẩu trước")
    cho = ratelimit.con_lai_giay(user.email, ip_cua(request))
    if cho:
        raise HTTPException(status_code=429, detail=f"Sai mật khẩu quá nhiều lần. Vui lòng thử lại sau {_cho(cho)}")
    if not verify_password(mat_khau, user.mat_khau_hash):
        ratelimit.ghi_that_bai(user.email, ip_cua(request))
        raise HTTPException(status_code=400, detail="Mật khẩu hiện tại không đúng")


@router.post("/api/v1/auth/doi-mat-khau")
def doi_mat_khau(body: DoiMatKhau, request: Request, user: models.NguoiDung = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    if user.co_mat_khau:          # tài khoản tạo bằng mạng xã hội: lần đầu ĐẶT mật khẩu, không cần mật khẩu cũ
        _xac_nhan_mat_khau(user, body.mat_khau_cu, request)
    loi = kiem_tra_mat_khau(body.mat_khau_moi, user.email, user.ho_ten)
    if loi:
        raise HTTPException(status_code=400, detail=loi)
    if verify_password(body.mat_khau_moi, user.mat_khau_hash):
        raise HTTPException(status_code=400, detail="Mật khẩu mới phải khác mật khẩu hiện tại")
    user.mat_khau_hash = hash_password(body.mat_khau_moi)
    user.mat_khau_doi_luc = datetime.now(timezone.utc)
    user.co_mat_khau = True
    db.commit()
    n = phien.thu_hoi_tat_ca(db, user.id, tru_sid=getattr(request.state, "sid", None), ly_do="doi_mat_khau")
    logbus.ghi("WARN", "auth", "doi_mat_khau", f"Đổi mật khẩu, đóng {n} phiên khác", nguoi_dung=user.email, ip=ip_cua(request))
    return {"message": f"Đổi mật khẩu thành công. Đã đăng xuất {n} thiết bị khác."}


# =================================================================== XÁC THỰC 2 LỚP
class XacNhanMatKhau(BaseModel):
    mat_khau: str = Field(max_length=128)


class MaSauSo(BaseModel):
    ma: str = Field(min_length=6, max_length=20)


class TatHaiLop(BaseModel):
    mat_khau: str = Field(max_length=128)
    ma: str = Field(min_length=6, max_length=20)


@router.post("/api/v1/auth/2fa/bat-dau")
def bat_dau_2fa(body: XacNhanMatKhau, request: Request, user: models.NguoiDung = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """Bước 1: tạo bí mật TOTP + mã QR. Chưa bật cho tới khi người dùng nhập đúng mã đầu tiên (bước 2)."""
    _xac_nhan_mat_khau(user, body.mat_khau, request)
    if user.totp_bat:
        raise HTTPException(status_code=400, detail="Xác thực 2 lớp đã được bật")
    bi_mat = phien.tao_bi_mat_totp()
    user.totp_bi_mat = phien.ma_hoa_bi_mat(bi_mat)
    user.totp_buoc_cuoi = None
    db.commit()
    uri = phien.uri_totp(bi_mat, user.email)
    return {"bi_mat": bi_mat, "uri": uri, "qr_svg": phien.qr_svg(uri)}


@router.post("/api/v1/auth/2fa/xac-nhan")
def xac_nhan_2fa(body: MaSauSo, request: Request, user: models.NguoiDung = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """Bước 2: nhập mã 6 số từ ứng dụng xác thực → bật 2 lớp, trả về 8 mã dự phòng (chỉ hiện 1 lần)."""
    cho = ratelimit.vuot_gioi_han("2fa", user.email, toi_da=5, cua_so_giay=300)
    if cho:
        raise HTTPException(status_code=429, detail=f"Nhập sai mã quá nhiều lần. Vui lòng thử lại sau {_cho(cho)}")
    bi_mat = phien.giai_ma_bi_mat(user.totp_bi_mat)
    if user.totp_bat or not bi_mat:
        raise HTTPException(status_code=400, detail="Hãy bắt đầu bật xác thực 2 lớp trước")
    buoc = phien.kiem_tra_totp(bi_mat, body.ma, None)
    if buoc is None:
        raise HTTPException(status_code=400, detail="Mã không đúng. Kiểm tra giờ trên điện thoại đã tự động chưa")
    ds_ma, json_bam = phien.tao_ma_du_phong()
    user.totp_bat, user.totp_buoc_cuoi, user.ma_du_phong = True, buoc, json_bam
    db.commit()
    n = phien.thu_hoi_tat_ca(db, user.id, tru_sid=getattr(request.state, "sid", None), ly_do="bat_2fa")
    logbus.ghi("WARN", "auth", "bat_2fa", f"Bật xác thực 2 lớp, đóng {n} phiên khác", nguoi_dung=user.email, ip=ip_cua(request))
    return {"message": "Đã bật xác thực 2 lớp", "ma_du_phong": ds_ma}


@router.post("/api/v1/auth/2fa/tat")
def tat_2fa(body: TatHaiLop, request: Request, user: models.NguoiDung = Depends(get_current_user),
            db: Session = Depends(get_db)):
    _xac_nhan_mat_khau(user, body.mat_khau, request)
    if not user.totp_bat:
        raise HTTPException(status_code=400, detail="Xác thực 2 lớp chưa bật")
    bi_mat = phien.giai_ma_bi_mat(user.totp_bi_mat)
    hop_le = (bi_mat and phien.kiem_tra_totp(bi_mat, body.ma, user.totp_buoc_cuoi) is not None) or \
        phien.dung_ma_du_phong(user.ma_du_phong, body.ma) is not None
    if not hop_le:
        raise HTTPException(status_code=400, detail="Mã xác thực không đúng")
    user.totp_bat, user.totp_bi_mat, user.totp_buoc_cuoi, user.ma_du_phong = False, None, None, None
    db.commit()
    logbus.ghi("WARN", "auth", "tat_2fa", "Tắt xác thực 2 lớp", nguoi_dung=user.email, ip=ip_cua(request))
    return {"message": "Đã tắt xác thực 2 lớp"}


@router.post("/api/v1/auth/2fa/ma-du-phong-moi")
def ma_du_phong_moi(body: TatHaiLop, request: Request, user: models.NguoiDung = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    _xac_nhan_mat_khau(user, body.mat_khau, request)
    bi_mat = phien.giai_ma_bi_mat(user.totp_bi_mat)
    buoc = phien.kiem_tra_totp(bi_mat, body.ma, user.totp_buoc_cuoi) if (user.totp_bat and bi_mat) else None
    if buoc is None:
        raise HTTPException(status_code=400, detail="Mã xác thực không đúng")
    ds_ma, json_bam = phien.tao_ma_du_phong()
    user.ma_du_phong, user.totp_buoc_cuoi = json_bam, buoc
    db.commit()
    logbus.ghi("INFO", "auth", "ma_du_phong_moi", "Tạo lại mã dự phòng", nguoi_dung=user.email, ip=ip_cua(request))
    return {"ma_du_phong": ds_ma}


# =================================================================== QUÊN MẬT KHẨU (OTP qua email)
class QuenMatKhau(BaseModel):
    email: EmailStr


class XacNhanOtp(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=6, max_length=6)
    mat_khau_moi: str = Field(max_length=128)


THONG_BAO_CHUNG = "Nếu email đã đăng ký, mã OTP đã được gửi tới hộp thư (kiểm tra cả mục Spam). Mã có hiệu lực 10 phút."


@router.post("/api/v1/auth/quen-mat-khau")
def quen_mat_khau(body: QuenMatKhau, request: Request, db: Session = Depends(get_db)):
    """Luôn trả cùng một thông báo (không cho biết email có tồn tại hay không).
    Mã OTP CHỈ hiện trên màn hình khi OTP_DEMO=1 (máy cá nhân) — tuyệt đối không bật trên máy chủ công khai."""
    email = chuan_hoa_email(str(body.email))
    ip = ip_cua(request)
    cho = ratelimit.vuot_gioi_han("otp_ip", ip, toi_da=10, cua_so_giay=3600)
    if cho:
        raise HTTPException(status_code=429, detail=f"Yêu cầu quá nhiều lần. Vui lòng thử lại sau {_cho(cho)}")
    if phien.otp_gan_day(db, email, 60):
        raise HTTPException(status_code=429, detail="Vui lòng đợi 1 phút trước khi yêu cầu mã mới")

    user = db.query(models.NguoiDung).filter(models.NguoiDung.email == email).first()
    if not user or user.bi_khoa:
        logbus.ghi("WARN", "auth", "otp_email_khong_ton_tai", "Yêu cầu OTP cho email chưa đăng ký/bị khóa", nguoi_dung=email, ip=ip)
        return {"message": THONG_BAO_CHUNG}

    ma = phien.tao_otp(db, email, ip)
    try:
        da_gui = gui_email_otp(email, ma)
    except Exception as exc:
        logbus.ghi("ERROR", "mail", "gui_otp_that_bai", f"{type(exc).__name__}: {exc}", nguoi_dung=email)
        da_gui = False
    logbus.ghi("INFO", "auth", "tao_otp", "Tạo mã OTP đặt lại mật khẩu" + ("" if da_gui else " (chưa gửi được email)"),
               nguoi_dung=email, ip=ip)
    if not da_gui and _bat("OTP_DEMO"):
        return {"message": "Chế độ demo (OTP_DEMO=1): chưa gửi được email, mã hiển thị bên dưới", "otp_demo": ma}
    return {"message": THONG_BAO_CHUNG}


@router.post("/api/v1/auth/xac-nhan-otp")
def xac_nhan_otp(body: XacNhanOtp, request: Request, db: Session = Depends(get_db)):
    """Xác nhận OTP và đặt mật khẩu mới; đóng mọi phiên đăng nhập cũ của tài khoản."""
    email = chuan_hoa_email(str(body.email))
    ip = ip_cua(request)
    cho = ratelimit.vuot_gioi_han("otp_xac_nhan", ip, toi_da=20, cua_so_giay=3600)
    if cho:
        raise HTTPException(status_code=429, detail=f"Thử quá nhiều lần. Vui lòng thử lại sau {_cho(cho)}")
    user = db.query(models.NguoiDung).filter(models.NguoiDung.email == email).first()
    loi = kiem_tra_mat_khau(body.mat_khau_moi, email, user.ho_ten if user else "")
    if loi:
        raise HTTPException(status_code=400, detail=loi)
    if not user or not phien.xac_nhan_otp(db, email, body.otp):
        logbus.ghi("WARN", "auth", "sai_otp", "Mã OTP sai hoặc hết hạn", nguoi_dung=email, ip=ip)
        raise HTTPException(status_code=400, detail="Mã OTP không đúng hoặc đã hết hạn")

    user.mat_khau_hash = hash_password(body.mat_khau_moi)
    user.mat_khau_doi_luc = datetime.now(timezone.utc)
    user.co_mat_khau = True
    db.commit()
    n = phien.thu_hoi_tat_ca(db, user.id, ly_do="dat_lai_mat_khau")
    ratelimit.xoa(email, ip)
    logbus.ghi("WARN", "auth", "dat_lai_mat_khau", f"Đặt lại mật khẩu bằng OTP, đóng {n} phiên", nguoi_dung=email, ip=ip)
    return {"message": "Đặt lại mật khẩu thành công"}
