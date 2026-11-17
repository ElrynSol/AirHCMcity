"""Ánh xạ các bảng CSDL với PostGIS."""

from sqlalchemy import Column, Integer, BigInteger, String, Text, Boolean, Float, Date, DateTime, ForeignKey
from geoalchemy2 import Geometry
from sqlalchemy.sql import func
from database import Base


class NguoiDung(Base):
    __tablename__ = "nguoi_dung"

    id = Column(Integer, primary_key=True, index=True)
    ho_ten = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    mat_khau_hash = Column(String(255), nullable=False)
    vai_tro = Column(String(20), default="viewer")  # admin | viewer
    ngay_tao = Column(DateTime(timezone=True), server_default=func.now())
    # Bảo mật (CSDL cũ được thêm cột tự động bởi core/phien.py khi khởi động)
    totp_bat = Column(Boolean, nullable=False, default=False, server_default="false")   # đã bật xác thực 2 lớp
    totp_bi_mat = Column(Text)            # bí mật TOTP đã mã hóa Fernet
    totp_buoc_cuoi = Column(BigInteger)   # bước thời gian của mã TOTP dùng gần nhất (chống dùng lại)
    ma_du_phong = Column(Text)            # JSON danh sách băm SHA-256 của mã dự phòng
    mat_khau_doi_luc = Column(DateTime(timezone=True))
    dang_nhap_cuoi = Column(DateTime(timezone=True))
    bi_khoa = Column(Boolean, nullable=False, default=False, server_default="false")   # admin khóa tài khoản
    co_mat_khau = Column(Boolean, nullable=False, default=True, server_default="true")  # False: tài khoản tạo bằng Google/Facebook/Zalo, chưa đặt mật khẩu


class TramQuanTrac(Base):
    __tablename__ = "tram_quan_trac"

    id = Column(Integer, primary_key=True, index=True)
    ma_tram = Column(String(20), unique=True)
    ten_tram = Column(String(255), nullable=False)
    toado = Column(Geometry(geometry_type='POINT', srid=4326))
    trang_thai = Column(String(50), default="Hoat Dong")