"""Tra cứu nhật ký hệ thống và trạng thái bus sự kiện (chỉ admin)."""

from core import config  # noqa: F401
from database import get_db
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
import models
from core import events
from core.security import require_admin

router = APIRouter()


@router.get("/api/v1/admin/nhat-ky")
def ds_nhat_ky(muc: str = None, nguon: str = None, q: str = None, gio: int = 24, limit: int = 200,
               admin: models.NguoiDung = Depends(require_admin), db: Session = Depends(get_db)):
    limit = max(1, min(limit, 1000))
    gio = max(1, min(gio, 24 * 90))
    dieu_kien = ["thoi_gian >= NOW() - (:gio * INTERVAL '1 hour')"]
    tham_so = {"gio": gio, "limit": limit}
    if muc:
        dieu_kien.append("muc = :muc")
        tham_so["muc"] = muc.upper()
    if nguon:
        dieu_kien.append("nguon = :nguon")
        tham_so["nguon"] = nguon
    if q:
        dieu_kien.append("(noi_dung ILIKE :q OR su_kien ILIKE :q OR nguoi_dung ILIKE :q)")
        tham_so["q"] = f"%{q}%"
    rows = db.execute(text(f"""
        SELECT id, thoi_gian, muc, nguon, su_kien, noi_dung, nguoi_dung
        FROM nhat_ky_he_thong WHERE {' AND '.join(dieu_kien)} ORDER BY id DESC LIMIT :limit
    """), tham_so).fetchall()
    return [{"id": r.id, "thoi_gian": r.thoi_gian.strftime("%Y-%m-%d %H:%M:%S"), "muc": r.muc, "nguon": r.nguon,
             "su_kien": r.su_kien, "noi_dung": r.noi_dung, "nguoi_dung": r.nguoi_dung} for r in rows]


@router.get("/api/v1/admin/nhat-ky/tong-hop")
def tong_hop_nhat_ky(gio: int = 24, admin: models.NguoiDung = Depends(require_admin), db: Session = Depends(get_db)):
    gio = max(1, min(gio, 24 * 90))
    rows = db.execute(text("""
        SELECT muc, nguon, COUNT(*) AS n FROM nhat_ky_he_thong
        WHERE thoi_gian >= NOW() - (:gio * INTERVAL '1 hour') GROUP BY muc, nguon
    """), {"gio": gio}).fetchall()
    theo_muc, theo_nguon = {}, {}
    for r in rows:
        theo_muc[r.muc] = theo_muc.get(r.muc, 0) + r.n
        theo_nguon[r.nguon] = theo_nguon.get(r.nguon, 0) + r.n
    return {"gio": gio, "theo_muc": theo_muc, "theo_nguon": theo_nguon, "bus_su_kien": events.thong_ke()}
