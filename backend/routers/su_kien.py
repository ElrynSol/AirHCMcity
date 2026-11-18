"""Luồng sự kiện thời gian thực cho trình duyệt (Server-Sent Events).

GET /api/v1/su-kien?chu_de=du_lieu.da_nap,dong_bo.xong   (bỏ chu_de: nhận mọi chủ đề công khai)
Trình duyệt dùng EventSource; mỗi sự kiện có tên = chủ đề, data = JSON. Gửi ': ping' mỗi 15 giây để giữ kết nối
(qua proxy) và phát hiện trình duyệt đã đóng.
Mỗi luồng tự đóng sau TUOI_LUONG giây, EventSource tự nối lại sau 1 giây: máy chủ tắt/nạp lại (uvicorn --reload)
không bị kẹt chờ các luồng mở mãi, trình duyệt luôn nối vào tiến trình máy chủ mới nhất.
"""

from core import config  # noqa: F401
import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from core import day_su_kien

router = APIRouter()
TUOI_LUONG = 25          # giây


@router.get("/api/v1/su-kien")
async def su_kien(request: Request, chu_de: str = None):
    loc = [c.strip() for c in chu_de.split(",") if c.strip() in day_su_kien.CHU_DE_DAY] if chu_de else None
    q = asyncio.Queue(maxsize=200)
    day_su_kien.dang_ky(q, asyncio.get_running_loop(), loc)

    async def luong():
        het_han = asyncio.get_running_loop().time() + TUOI_LUONG
        try:
            yield "retry: 1000\n\n"
            yield f"event: ket_noi\ndata: {json.dumps({'chu_de': loc or list(day_su_kien.CHU_DE_DAY)})}\n\n"
            while asyncio.get_running_loop().time() < het_han:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(q.get(), timeout=min(15, max(0.1, het_han - asyncio.get_running_loop().time())))
                    yield f"event: {item['chu_de']}\ndata: {json.dumps(item['du_lieu'], ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            day_su_kien.huy(q)

    return StreamingResponse(luong(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})


@router.get("/api/v1/su-kien/trang-thai")
def trang_thai():
    return {"so_ket_noi": day_su_kien.so_ket_noi(), "chu_de": list(day_su_kien.CHU_DE_DAY), **day_su_kien.thong_ke}
