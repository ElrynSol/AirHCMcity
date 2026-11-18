"""API khảo sát SUS: GET câu hỏi, POST phiếu (không cần đăng nhập, giới hạn 3 phiếu/giờ/IP), GET kết quả tổng hợp (công khai)."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core import ratelimit
from core.security import ip_cua
from services import khao_sat as ks

router = APIRouter()


class Phieu(BaseModel):
    vai_tro: str
    tra_loi: list[int] = Field(min_length=10, max_length=10)
    y_kien: str | None = Field(default=None, max_length=500)


@router.get("/api/v1/khao-sat/cau-hoi")
def cau_hoi():
    return {"cau_hoi": ks.CAU_HOI, "vai_tro": ks.VAI_TRO}


@router.post("/api/v1/khao-sat")
def gui(phieu: Phieu, request: Request):
    ip = ip_cua(request)
    cho = ratelimit.vuot_gioi_han("khao_sat", ks.bam_ip(ip), toi_da=3, cua_so_giay=3600)
    if cho:
        raise HTTPException(429, f"Bạn đã gửi nhiều phiếu. Thử lại sau {cho // 60 + 1} phút.")
    try:
        d = ks.them(phieu.vai_tro, phieu.tra_loi, phieu.y_kien, ip)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"diem_sus": d, "xep_hang": ks.xep_hang(d)}


@router.get("/api/v1/khao-sat/ket-qua")
def ket_qua():
    return ks.tong_hop()
