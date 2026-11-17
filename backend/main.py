"""API chính: lắp ráp các router. Chạy từ thư mục backend:  uvicorn main:app --reload"""

from core import config  # nạp .env + sys.path (phải đứng đầu)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import models
from database import engine

from routers import auth, tram, du_lieu, aqi, du_bao, admin_gee, bao_cao, thong_ke, canh_bao, nhat_ky, he_thong, luong_canh_bao, dong_thoi_gian, du_bao_gio, kich_ban, ban_do_nhiet, iot, dong_bo, tong_quan, su_kien, tro_ly, day, seo, oauth, phan_anh, ranh_gioi, ung_dung, khong_gian
from services.canh_bao_service import _tao_bang_canh_bao, _tao_bang_thu_da_gui, _vong_lap_canh_bao, dang_ky_consumer
from services import cdc
from services import iot as iot_service
from services import dong_bo as dong_bo_service
from services import day_thong_bao
from services import phan_anh as phan_anh_service
from core import events, logbus, day_su_kien, phien
from core.bao_mat_http import BaoMatHTTP
from core.seo import WebTinh
from fastapi import Request
from fastapi.responses import JSONResponse

models.Base.metadata.create_all(bind=engine)
phien.tao_bang(engine)   # bảng phiên đăng nhập, OTP, cột 2FA (CSDL cũ tự được nâng cấp)
_tao_bang_canh_bao()
_tao_bang_thu_da_gui()
logbus.tao_bang_nhat_ky()
phan_anh_service.tao_bang()   # phản ánh ô nhiễm từ người dân
try:   # ranh giới 168 phường/xã vào PostGIS nếu bảng còn trống (máy mới, Docker)
    from nap_ranh_gioi import nap_neu_trong
    nap_neu_trong(engine)
except Exception as _loi_rg:
    logbus.ghi("WARN", "he_thong", "nap_ranh_gioi", f"{type(_loi_rg).__name__}: {_loi_rg}")

app = FastAPI(title="Hệ thống Quản lý Chất lượng Không khí TP.HCM",
              docs_url=None if config.MOI_TRUONG == "production" else "/docs",
              redoc_url=None, openapi_url=None if config.MOI_TRUONG == "production" else "/openapi.json")
app.add_middleware(BaoMatHTTP)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)



@app.middleware("http")
async def ghi_loi_may_chu(request: Request, call_next):
    """Gom mọi lỗi 5xx (ngoại lệ không bắt) vào nhật ký tập trung."""
    try:
        response = await call_next(request)
    except Exception as exc:
        logbus.ghi("ERROR", "api", "loi_5xx", f"{request.method} {request.url.path}: {type(exc).__name__}: {exc}")
        return JSONResponse({"detail": "Lỗi máy chủ"}, status_code=500)
    if response.status_code >= 500:
        logbus.ghi("ERROR", "api", "loi_5xx", f"{request.method} {request.url.path} -> {response.status_code}")
    return response


for _router in (auth, tram, du_lieu, aqi, du_bao, admin_gee, bao_cao, thong_ke, canh_bao, nhat_ky, he_thong, luong_canh_bao, dong_thoi_gian, du_bao_gio, kich_ban, ban_do_nhiet, iot, dong_bo, tong_quan, su_kien, tro_ly, day, seo, oauth, phan_anh, ranh_gioi, ung_dung, khong_gian):
    app.include_router(_router.router)


@app.on_event("startup")
def khoi_dong_canh_bao():
    import threading
    dang_ky_consumer()
    events.khoi_dong()   # luồng xử lý sự kiện
    day_su_kien.khoi_dong()  # chuyển tiếp sự kiện công khai tới trình duyệt (SSE)
    cdc.tao_trigger()    # trigger NOTIFY trên tram_quan_trac / du_lieu_tram_mat_dat
    cdc.khoi_dong()      # luồng LISTEN
    iot_service.khoi_dong()  # MQTT: trạm IoT mô phỏng (Wokwi) + phát AQI cho bảng điện tử
    dong_bo_service.khoi_dong()  # lịch tự đồng bộ dữ liệu + tự lấy bù ngày thiếu
    day_thong_bao.khoi_dong()    # thông báo đẩy (Web Push) khi AQI vượt ngưỡng, chạy nền mỗi 30 phút
    logbus.ghi("INFO", "he_thong", "khoi_dong", "Máy chủ đã khởi động")
    threading.Thread(target=_vong_lap_canh_bao, daemon=True).start()


# Phải đứng CUỐI: phục vụ giao diện web tĩnh (đường dẫn tuyệt đối: chạy được từ mọi thư mục, mọi hệ điều hành)
# WebTinh = StaticFiles + tự chèn thẻ SEO (canonical, Open Graph, JSON-LD) vào trang HTML
app.mount("/", WebTinh(directory=str(config.PROJECT_ROOT / "frontend"), html=True), name="frontend")
