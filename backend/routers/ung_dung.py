"""Tải ứng dụng: phục vụ tệp APK Android và thông tin + mã QR cho trang tai-app.html.

- Android: tải mobile/AirHCM.apk trực tiếp (cài ngoài Google Play, cần cho phép "cài ứng dụng không rõ nguồn gốc").
- iPhone/iPad: Apple không cho cài tệp ngoài App Store → dùng web dạng PWA ("Thêm vào Màn hình chính"),
  chạy toàn màn hình, có biểu tượng, nhận thông báo đẩy (iOS 16.4+).
"""

import hashlib
import socket
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from core import config

router = APIRouter(tags=["Tải ứng dụng"])
TEP_APK = config.PROJECT_ROOT / "mobile" / "AirHCM.apk"
_bam = {}


def _sha256(p):
    k = (str(p), p.stat().st_mtime)
    if k not in _bam:
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for khoi in iter(lambda: f.read(1 << 20), b""):
                h.update(khoi)
        _bam.clear()
        _bam[k] = h.hexdigest()
    return _bam[k]


def _ip_lan():
    """IP Wi-Fi của máy chủ (khi chạy trên máy cá nhân, điện thoại cùng mạng dùng IP này thay cho localhost)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


@router.get("/tai/AirHCM.apk", include_in_schema=False)
def tai_apk():
    if not TEP_APK.exists():
        raise HTTPException(404, "Chưa có tệp cài đặt Android. Build bằng: cd mobile && npm run apk")
    return FileResponse(TEP_APK, media_type="application/vnd.android.package-archive", filename="AirHCM.apk",
                        headers={"Cache-Control": "no-cache"})


@router.get("/api/v1/ung-dung")
def thong_tin(request: Request):
    goc = config.DIA_CHI_CONG_KHAI or f"{request.url.scheme}://{request.url.netloc}"
    cuc_bo = request.url.hostname in ("localhost", "127.0.0.1", "::1")
    if cuc_bo and not config.DIA_CHI_CONG_KHAI:
        ip = _ip_lan()   # "localhost" trên điện thoại là chính điện thoại → thay bằng IP Wi-Fi của máy chủ
        if ip:
            goc = f"{request.url.scheme}://{ip}:{request.url.port or 80}"
    trang = goc + "/tai-app.html"
    apk = None
    if TEP_APK.exists():
        st = TEP_APK.stat()
        apk = {"duong_dan": "/tai/AirHCM.apk", "kich_thuoc_mb": round(st.st_size / 1048576, 1),
               "cap_nhat": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="minutes"), "sha256": _sha256(TEP_APK)}
    from core.phien import qr_svg
    return {"trang_tai": trang, "dia_chi_web": goc, "qr_svg": qr_svg(trang), "apk": apk,
            "mang_noi_bo": cuc_bo or goc.startswith("http://"),
            "ghi_chu": None if goc.startswith("https://") else
            "Đang chạy trên máy cá nhân: điện thoại phải cùng mạng Wi-Fi với máy này. Thông báo nền và định vị trên điện thoại cần HTTPS (bản triển khai lên Internet)."}
