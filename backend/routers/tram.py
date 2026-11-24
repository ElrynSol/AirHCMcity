"""Quản lý điểm ước tính (CRUD) và dữ liệu theo trạm."""

from core import config  # noqa: F401  (nạp .env và đường dẫn dự án trước)
from database import get_db
from fastapi import Depends
from fastapi import HTTPException
from geoalchemy2.shape import from_shape
from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import List
import models
import schemas
from fastapi import APIRouter
from core.security import require_admin
from core import logbus
from services import ranh_gioi as rg

router = APIRouter()


def tram_to_out(tram: models.TramQuanTrac) -> schemas.TramOut:
    vi_do, kinh_do = None, None
    if tram.toado is not None:
        point = to_shape(tram.toado)
        vi_do, kinh_do = point.y, point.x
    return schemas.TramOut(
        id=tram.id, ma_tram=tram.ma_tram, ten_tram=tram.ten_tram,
        vi_do=vi_do, kinh_do=kinh_do, trang_thai=tram.trang_thai
    )


@router.get("/api/v1/tram", response_model=List[schemas.TramOut])
def get_all_tram(db: Session = Depends(get_db)):
    tram_list = db.query(models.TramQuanTrac).all()
    return [tram_to_out(t) for t in tram_list]


@router.get("/api/v1/tram/{tram_id}", response_model=schemas.TramOut)
def get_tram(tram_id: int, db: Session = Depends(get_db)):
    tram = db.query(models.TramQuanTrac).filter(models.TramQuanTrac.id == tram_id).first()
    if not tram:
        raise HTTPException(status_code=404, detail="Không tìm thấy trạm")
    return tram_to_out(tram)


def _kiem_tra_trong_tp(vi_do: float, kinh_do: float) -> None:
    """Chặn tọa độ nằm ngoài 168 phường/xã TP.HCM (ST_Contains trên bảng phuong_xa).
    Nếu CSDL chưa nạp ranh giới thì bỏ qua để không khóa chức năng quản trị."""
    if not rg.co_du_lieu():
        return
    if rg.phuong_chua_diem(vi_do, kinh_do) is None:
        raise HTTPException(status_code=400, detail="Vị trí nằm ngoài ranh giới 168 phường/xã của TP.HCM")


@router.post("/api/v1/tram", response_model=schemas.TramOut)
def create_tram(
    tram: schemas.TramCreate,
    db: Session = Depends(get_db),
    admin: models.NguoiDung = Depends(require_admin)
):
    _kiem_tra_trong_tp(tram.vi_do, tram.kinh_do)
    point = from_shape(Point(tram.kinh_do, tram.vi_do), srid=4326)
    new_tram = models.TramQuanTrac(
        ma_tram=tram.ma_tram.strip(), ten_tram=tram.ten_tram.strip(), toado=point, trang_thai=tram.trang_thai
    )
    db.add(new_tram)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Mã điểm '{tram.ma_tram}' đã tồn tại")
    db.refresh(new_tram)
    logbus.ghi("INFO", "tram", "admin_them_tram", f"Thêm trạm {new_tram.ma_tram} - {new_tram.ten_tram}", nguoi_dung=admin.email)
    return tram_to_out(new_tram)


@router.put("/api/v1/tram/{tram_id}", response_model=schemas.TramOut)
def update_tram(
    tram_id: int,
    tram_update: schemas.TramUpdate,
    db: Session = Depends(get_db),
    admin: models.NguoiDung = Depends(require_admin)
):
    tram = db.query(models.TramQuanTrac).filter(models.TramQuanTrac.id == tram_id).first()
    if not tram:
        raise HTTPException(status_code=404, detail="Không tìm thấy trạm")

    if tram_update.ma_tram is not None:
        tram.ma_tram = tram_update.ma_tram.strip()
    if tram_update.ten_tram is not None:
        tram.ten_tram = tram_update.ten_tram.strip()
    if tram_update.trang_thai is not None:
        tram.trang_thai = tram_update.trang_thai
    if tram_update.vi_do is not None and tram_update.kinh_do is not None:
        _kiem_tra_trong_tp(tram_update.vi_do, tram_update.kinh_do)
        tram.toado = from_shape(Point(tram_update.kinh_do, tram_update.vi_do), srid=4326)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Mã điểm đã tồn tại ở điểm dữ liệu khác")
    db.refresh(tram)
    logbus.ghi("INFO", "tram", "admin_sua_tram", f"Sửa trạm {tram.ma_tram}", nguoi_dung=admin.email)
    return tram_to_out(tram)


@router.delete("/api/v1/tram/{tram_id}")
def delete_tram(
    tram_id: int,
    db: Session = Depends(get_db),
    admin: models.NguoiDung = Depends(require_admin)
):
    tram = db.query(models.TramQuanTrac).filter(models.TramQuanTrac.id == tram_id).first()
    if not tram:
        raise HTTPException(status_code=404, detail="Không tìm thấy trạm")
    ten_xoa = f"{tram.ma_tram} - {tram.ten_tram}"
    try:
        db.delete(tram)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Điểm dữ liệu đang có số liệu lịch sử hoặc đăng ký cảnh báo; hãy chuyển trạng thái sang 'Ngung' thay vì xóa hẳn.")
    logbus.ghi("WARN", "tram", "admin_xoa_tram", f"Xóa trạm {ten_xoa}", nguoi_dung=admin.email)
    return {"message": f"Đã xóa trạm '{tram.ten_tram}'"}


@router.get("/api/v1/tram/{tram_id}/du-lieu-moi-nhat")
def get_latest_data(tram_id: int, db: Session = Depends(get_db)):
    result = db.execute(text("""
        SELECT ngay_do, no2_mean, co_mean, so2_mean
        FROM du_lieu_gee_tphcm
        WHERE tram_id = :tram_id
        ORDER BY ngay_do DESC LIMIT 1
    """), {"tram_id": tram_id}).fetchone()

    if not result:
        return {"message": "Chưa có dữ liệu cho trạm này"}

    return {
        "ngay_do": str(result.ngay_do),
        "no2_mean": result.no2_mean,
        "co_mean": result.co_mean,
        "so2_mean": result.so2_mean
    }


@router.get("/api/v1/tram/{tram_id}/lich-su")
def get_history(tram_id: int, so_ngay: int = 30, db: Session = Depends(get_db)):
    so_ngay = max(1, min(so_ngay, 365))
    result = db.execute(text("""
        SELECT ngay_do, no2_mean, co_mean, so2_mean
        FROM du_lieu_gee_tphcm
        WHERE tram_id = :tram_id
        ORDER BY ngay_do DESC LIMIT :so_ngay
    """), {"tram_id": tram_id, "so_ngay": so_ngay}).fetchall()

    return [
        {"ngay_do": str(r.ngay_do), "no2": r.no2_mean, "co": r.co_mean, "so2": r.so2_mean}
        for r in reversed(result)
    ]
