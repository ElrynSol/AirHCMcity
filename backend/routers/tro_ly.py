"""API Trợ lý AirHCM: POST /api/v1/tro-ly  → luồng text/event-stream.

Thân yêu cầu: {"cau_hoi": "...", "lich_su": [{"vai": "user"|"assistant", "noi_dung": "..."}]}
Sự kiện trả về: che_do {che_do, model} → chu {t} (nhiều lần) → xong {...}  |  loi {thong_bao}
"""

from core import config  # noqa: F401
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from core import logbus
from services import tro_ly
from services.tong_quan import tong_quan

router = APIRouter()


def _sse(su_kien, du_lieu):
    return f"event: {su_kien}\ndata: {json.dumps(du_lieu, ensure_ascii=False)}\n\n"


@router.get("/api/v1/tro-ly/trang-thai")
def trang_thai():
    ncc = tro_ly.nha_cung_cap()
    return {"che_do": "ai" if ncc else "tu_dong", "nha_cung_cap": ncc, "model": tro_ly.ten_model(ncc),
            "goi_y": ["Hôm nay có nên chạy bộ buổi sáng không?", "Khu vực nào đang sạch nhất?",
                      "Tối nay không khí thế nào?", "Kiến trúc hệ thống gồm những gì?",
                      "AQI được tính theo cách nào?", "Số liệu có chính xác không?"]}


@router.post("/api/v1/tro-ly")
async def hoi(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Thân yêu cầu phải là JSON")
    cau_hoi = str((body or {}).get("cau_hoi") or "").strip()
    if not cau_hoi:
        raise HTTPException(status_code=400, detail="Chưa có câu hỏi")
    cau_hoi = cau_hoi[:tro_ly.DO_DAI_CAU_HOI]
    lich_su = tro_ly.lam_sach_lich_su((body or {}).get("lich_su"))
    ip = request.client.host if request.client else "?"
    ncc = tro_ly.nha_cung_cap()
    duoc, dung_ai, thong_bao = tro_ly.kiem_tra_gioi_han(ip, ncc is not None)
    if not duoc:
        raise HTTPException(status_code=429, detail=thong_bao)

    du_lieu = tong_quan()   # có đệm 60 giây

    async def luong():
        if dung_ai:
            yield _sse("che_do", {"che_do": "ai", "nha_cung_cap": ncc, "model": tro_ly.ten_model(ncc)})
            try:
                async for su_kien, d in tro_ly.luong_ai(cau_hoi, lich_su, du_lieu, ncc):
                    yield _sse(su_kien, d)
                    if su_kien == "xong":
                        logbus.ghi("INFO", "tro_ly", "tra_loi_ai", f"{d.get('nha_cung_cap')} {d.get('model')} · {d.get('stop_reason')} · token {d.get('token')}")
                return
            except Exception as exc:      # lỗi trước khi có chữ (khóa sai, hết hạn mức, mất mạng…) → trả lời tự động
                logbus.ghi("WARN", "tro_ly", "ai_loi", f"{type(exc).__name__}: {str(exc)[:300]}")
                yield _sse("che_do", {"che_do": "tu_dong", "ly_do": "Dịch vụ AI tạm thời không phản hồi, chuyển sang trả lời tự động."})
        else:
            yield _sse("che_do", {"che_do": "tu_dong"})
        yield _sse("chu", {"t": tro_ly.tra_loi_tu_dong(cau_hoi, du_lieu)})
        yield _sse("xong", {"che_do": "tu_dong"})

    return StreamingResponse(luong(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
