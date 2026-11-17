"""Lớp bảo vệ HTTP dùng chung cho mọi yêu cầu.

1. Header bảo mật (OWASP Secure Headers): CSP, chống nhúng iframe (clickjacking), chống đoán kiểu MIME,
   Referrer-Policy, Permissions-Policy; HSTS khi chạy HTTPS.
2. Chống CSRF lớp thứ hai (lớp thứ nhất là cookie SameSite=Strict): yêu cầu thay đổi dữ liệu (POST/PUT/PATCH/DELETE)
   có kèm cookie đăng nhập thì Origin/Referer phải là chính máy chủ hoặc miền nằm trong CORS_ORIGINS.
3. API trả dữ liệu cá nhân không được lưu cache (Cache-Control: private, no-store cho /api/v1/auth/* và mọi API
   cần đăng nhập) — service worker (sw.js) cũng bỏ qua các phản hồi này.
"""

from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from core.config import COOKIE_NAME, CORS_ORIGINS

_CDN_SCRIPT = "https://cdnjs.cloudflare.com https://cdn.jsdelivr.net https://unpkg.com"
CSP = "; ".join([
    "default-src 'self'",
    f"script-src 'self' 'unsafe-inline' {_CDN_SCRIPT}",           # trang dùng script nội tuyến + thư viện từ CDN
    f"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com {_CDN_SCRIPT}",
    "font-src 'self' data: https://fonts.gstatic.com https://cdnjs.cloudflare.com",
    "img-src 'self' data: blob: https:",                         # ảnh nền bản đồ (ArcGIS), biểu tượng Leaflet
    "connect-src 'self' https: wss:",                            # API ranh giới phường (GitHub), Open-Meteo...
    "worker-src 'self' blob:",
    "manifest-src 'self'",
    "frame-src 'self'",
    "frame-ancestors 'none'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
])
_PHUONG_THUC_GHI = {"POST", "PUT", "PATCH", "DELETE"}


def _nguon(url: str | None) -> str | None:
    if not url:
        return None
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}".lower() if p.scheme and p.netloc else None


class BaoMatHTTP(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        https = request.url.scheme == "https"

        if request.method in _PHUONG_THUC_GHI and request.cookies.get(COOKIE_NAME):
            nguon = _nguon(request.headers.get("origin")) or _nguon(request.headers.get("referer"))
            cua_minh = f"{request.url.scheme}://{request.url.netloc}".lower()
            duoc_phep = {cua_minh, *(o.lower().rstrip("/") for o in CORS_ORIGINS)}
            if nguon is not None and nguon not in duoc_phep:
                return JSONResponse({"detail": "Yêu cầu bị từ chối (sai nguồn gốc – nghi ngờ CSRF)"}, status_code=403)

        resp = await call_next(request)
        h = resp.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), payment=(), usb=(), geolocation=(self)")
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if "text/html" in h.get("content-type", ""):
            h.setdefault("Content-Security-Policy", CSP + ("; upgrade-insecure-requests" if https else ""))
        if https:
            h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        # Phản hồi chứa dữ liệu riêng của người đăng nhập (get_current_user đã gán request.state.sid) hoặc API xác thực:
        # cấm lưu ở bộ nhớ đệm trình duyệt/proxy/service worker (máy dùng chung không lộ dữ liệu sau khi đăng xuất)
        if request.url.path.startswith("/api/v1/auth") or getattr(request.state, "sid", None):
            h["Cache-Control"] = "private, no-store"
        return resp
