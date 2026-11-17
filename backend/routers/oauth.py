"""Đăng nhập / đăng ký / liên kết tài khoản bằng Google, Facebook, Zalo (xem core/oauth.py, docs/DANG_NHAP_MXH.md).

Luồng: trình duyệt → /oauth/<ncc>/bat-dau (tạo state + PKCE, lưu cookie ký số) → trang đồng ý của nhà cung cấp
→ /oauth/<ncc>/callback (kiểm state, đổi mã lấy hồ sơ) → tìm/tạo tài khoản → mở phiên (hoặc bước xác thực 2 lớp).

Quy tắc ghép tài khoản:
1. (nhà cung cấp, mã người dùng) đã liên kết → đăng nhập tài khoản đó.
2. Đang đăng nhập và bấm "Liên kết" ở trang Tài khoản → gắn vào tài khoản hiện tại.
3. Email do nhà cung cấp XÁC MINH trùng tài khoản có sẵn → tự gắn vào tài khoản đó.
4. Còn lại → tạo tài khoản mới (vai trò viewer; admin nếu email đã xác minh nằm trong ADMIN_EMAILS).
Tài khoản bật xác thực 2 lớp vẫn phải nhập mã 6 số sau khi đăng nhập bằng mạng xã hội.
"""

import hmac
import html
import json
import os
import re
import secrets
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from core import config  # noqa: F401
import models
from auth import create_access_token, decode_access_token, hash_password
from core import logbus, oauth, ratelimit
from core.security import chuan_hoa_email, doc_token, get_current_user, ip_cua
from database import get_db
from routers.auth import HAN_MA_TAM_2FA, _mo_phien

router = APIRouter(prefix="/api/v1/auth/oauth", tags=["Đăng nhập mạng xã hội"])
COOKIE_TAM = "oauth_tam"
DUONG_COOKIE = "/api/v1/auth/oauth"


def _bat(ten, mac_dinh="0"):
    return os.getenv(ten, mac_dinh).strip().lower() in ("1", "true", "yes", "on")


def _goc(request: Request) -> str:
    return config.DIA_CHI_CONG_KHAI or f"{request.url.scheme}://{request.url.netloc}"


def _redirect_uri(request: Request, ncc: str) -> str:
    return f"{_goc(request)}/api/v1/auth/oauth/{ncc}/callback"


def _trang_tiep(t: str | None) -> str:
    t = t or ""
    return t if re.fullmatch(r"[a-z0-9-]+\.html([?#][^\s<>\"']*)?", t, re.I) and not t.lower().startswith("login.html") else "tong-quan.html"


def _chuyen(url: str) -> HTMLResponse:
    """Chuyển trang bằng JavaScript thay vì HTTP 302: lượt điều hướng xuất phát từ chính trang của mình
    nên cookie phiên SameSite=Strict vừa đặt được gửi kèm ngay (302 nối tiếp từ trang nhà cung cấp thì không)."""
    # Trang này nằm ở /api/v1/auth/oauth/<ncc>/callback → phải chuyển về đường dẫn tính từ GỐC web ("/iot.html"),
    # nếu không trình duyệt hiểu "iot.html" thành /api/v1/auth/oauth/<ncc>/iot.html (404)
    if not url.startswith("/"):
        url = "/" + url
    u = json.dumps(url)
    return HTMLResponse(f"""<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="robots" content="noindex">
<meta http-equiv="refresh" content="1;url={html.escape(url, quote=True)}"><title>Đang chuyển…</title></head>
<body style="font-family:system-ui;text-align:center;padding:40px;color:#344054">Đang đăng nhập…
<script>location.replace({u});</script></body></html>""", headers={"Cache-Control": "no-store"})


def _loi(thong_diep: str, tai_khoan: bool = False) -> HTMLResponse:
    trang = "tai-khoan.html?loi_lk=" if tai_khoan else "login.html?loi="
    return _chuyen(trang + quote(thong_diep))


@router.get("/nha-cung-cap")
def nha_cung_cap():
    """Các nhà cung cấp đã cấu hình khóa (trang đăng nhập chỉ hiện nút của những nhà cung cấp này)."""
    return {"nha_cung_cap": oauth.ds_da_cau_hinh()}


@router.get("/{ncc}/bat-dau")
def bat_dau(ncc: str, request: Request, ghi_nho: int = 0, tiep: str | None = None, lien_ket: int = 0):
    if not oauth.da_cau_hinh(ncc):
        return _loi(f"Đăng nhập bằng {ncc} chưa được cấu hình trên máy chủ")
    # Google/Facebook chỉ chấp nhận địa chỉ trả về đã khai báo (http://localhost:8000/...). Mở web bằng 127.0.0.1
    # thì chuyển sang localhost TRƯỚC khi bắt đầu, để cookie state và cookie phiên cùng một địa chỉ.
    if not config.DIA_CHI_CONG_KHAI and request.url.hostname in ("127.0.0.1", "::1", "[::1]"):
        return RedirectResponse(str(request.url.replace(hostname="localhost")), status_code=302)
    uid = None
    if lien_ket:   # liên kết thêm vào tài khoản đang đăng nhập (cookie phiên SameSite=Strict có mặt vì bấm từ trang của mình)
        t = doc_token(request)
        p = decode_access_token(t, loai="phien") if t else None
        if not p:
            return _loi("Hãy đăng nhập trước khi liên kết tài khoản")
        uid = p.get("sub")
    state = secrets.token_urlsafe(24)
    verifier, challenge = oauth.tao_pkce()
    tam = create_access_token({"typ": "oauth", "ncc": ncc, "state": state, "pkce": verifier, "ghi_nho": bool(ghi_nho),
                               "tiep": _trang_tiep(tiep), "lien_ket": uid}, het_han_giay=oauth.HAN_STATE_GIAY)
    resp = RedirectResponse(oauth.url_uy_quyen(ncc, _redirect_uri(request, ncc), state, challenge), status_code=302)
    # SameSite=Lax: cookie được gửi lại khi nhà cung cấp chuyển hướng (điều hướng GET cấp cao nhất) về callback
    resp.set_cookie(COOKIE_TAM, tam, max_age=oauth.HAN_STATE_GIAY, path=DUONG_COOKIE, httponly=True, samesite="lax",
                    secure=request.url.scheme == "https" or _bat("COOKIE_SECURE"))
    return resp


@router.get("/{ncc}/callback")
def callback(ncc: str, request: Request, code: str | None = None, state: str | None = None, error: str | None = None,
             db: Session = Depends(get_db)):
    tam = decode_access_token(request.cookies.get(COOKIE_TAM) or "", loai="oauth")
    lien_ket = bool(tam and tam.get("lien_ket"))

    def ket_thuc(resp):
        resp.delete_cookie(COOKIE_TAM, path=DUONG_COOKIE)
        return resp

    if error:
        return ket_thuc(_loi("Bạn đã hủy đăng nhập" if error in ("access_denied", "user_cancelled") else f"Nhà cung cấp báo lỗi: {error}", lien_ket))
    if not tam or tam.get("ncc") != ncc or not state or not hmac.compare_digest(str(tam.get("state")), state) or not code:
        logbus.ghi("WARN", "auth", "oauth_state_sai", f"State OAuth {ncc} không khớp hoặc hết hạn", ip=ip_cua(request))
        return ket_thuc(_loi("Phiên đăng nhập đã hết hạn hoặc không hợp lệ, vui lòng thử lại", lien_ket))

    try:
        hs = oauth.doi_ma_lay_ho_so(ncc, code, tam["pkce"], _redirect_uri(request, ncc))
    except oauth.LoiOAuth as exc:
        logbus.ghi("WARN", "auth", "oauth_loi", f"{ncc}: {exc}", ip=ip_cua(request))
        return ket_thuc(_loi(str(exc), lien_ket))
    except Exception as exc:   # mạng tới nhà cung cấp
        logbus.ghi("ERROR", "auth", "oauth_loi", f"{ncc}: {type(exc).__name__}: {exc}", ip=ip_cua(request))
        return ket_thuc(_loi(f"Không kết nối được {oauth.NHA_CUNG_CAP[ncc]['ten']}, vui lòng thử lại", lien_ket))

    lk = db.execute(text("SELECT nguoi_dung_id FROM lien_ket_mxh WHERE nha_cung_cap = :n AND ma_ngoai = :m"),
                    {"n": ncc, "m": hs.ma}).fetchone()
    ten_ncc = oauth.NHA_CUNG_CAP[ncc]["ten"]

    # --- (2) Liên kết thêm vào tài khoản đang đăng nhập
    if lien_ket:
        user = db.query(models.NguoiDung).filter(models.NguoiDung.email == tam["lien_ket"]).first()
        if not user:
            return ket_thuc(_loi("Tài khoản không tồn tại", True))
        if lk and lk.nguoi_dung_id != user.id:
            return ket_thuc(_loi(f"Tài khoản {ten_ncc} này đã gắn với một tài khoản AirHCM khác", True))
        if not lk:
            if db.execute(text("SELECT 1 FROM lien_ket_mxh WHERE nguoi_dung_id = :u AND nha_cung_cap = :n"),
                          {"u": user.id, "n": ncc}).fetchone():
                return ket_thuc(_loi(f"Tài khoản đã liên kết một tài khoản {ten_ncc} khác. Hãy gỡ liên kết cũ trước", True))
            _them_lien_ket(db, user.id, hs)
        logbus.ghi("WARN", "auth", "lien_ket_mxh", f"Liên kết {ten_ncc}", nguoi_dung=user.email, ip=ip_cua(request))
        return ket_thuc(_chuyen("tai-khoan.html?lien_ket=" + ncc))

    # --- (1) Đã liên kết trước đó
    user = db.get(models.NguoiDung, lk.nguoi_dung_id) if lk else None
    # --- (3) Email đã xác minh trùng tài khoản có sẵn
    if user is None and hs.email and hs.email_da_xac_minh:
        user = db.query(models.NguoiDung).filter(models.NguoiDung.email == chuan_hoa_email(hs.email)).first()
        if user:
            _them_lien_ket(db, user.id, hs)
            logbus.ghi("WARN", "auth", "tu_lien_ket_mxh", f"Tự gắn {ten_ncc} vào tài khoản có cùng email đã xác minh",
                       nguoi_dung=user.email, ip=ip_cua(request))
    # --- (4) Tạo tài khoản mới
    if user is None:
        if not _bat("CHO_PHEP_DANG_KY", "1"):
            return ket_thuc(_loi("Hệ thống đang tạm khóa đăng ký tài khoản mới"))
        if ratelimit.vuot_gioi_han("dang_ky", ip_cua(request), toi_da=5, cua_so_giay=3600):
            return ket_thuc(_loi("Đăng ký quá nhiều lần, vui lòng thử lại sau"))
        email = chuan_hoa_email(hs.email) if (hs.email and hs.email_da_xac_minh) else f"{ncc}-{hs.ma}@mxh.airhcm.invalid"
        ds_admin = {chuan_hoa_email(e) for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()}
        user = models.NguoiDung(ho_ten=(hs.ho_ten or f"Người dùng {ten_ncc}")[:100], email=email,
                                mat_khau_hash=hash_password(secrets.token_urlsafe(32)),   # không ai biết → không đăng nhập bằng mật khẩu được
                                vai_tro="admin" if (hs.email_da_xac_minh and email in ds_admin) else "viewer",
                                co_mat_khau=False)
        db.add(user)
        db.commit()
        db.refresh(user)
        _them_lien_ket(db, user.id, hs)
        logbus.ghi("INFO", "auth", "dang_ky_mxh", f"Tài khoản mới qua {ten_ncc} ({user.vai_tro})", nguoi_dung=user.email,
                   ip=ip_cua(request))

    if user.bi_khoa:
        return ket_thuc(_loi("Tài khoản đã bị quản trị viên khóa"))
    db.execute(text("UPDATE lien_ket_mxh SET dang_nhap_cuoi = NOW() WHERE nha_cung_cap = :n AND ma_ngoai = :m"),
               {"n": ncc, "m": hs.ma})
    db.commit()

    if user.totp_bat:   # vẫn bắt buộc bước 2 lớp
        ma_tam = create_access_token({"sub": user.email, "typ": "2fa", "ghi_nho": bool(tam.get("ghi_nho"))},
                                     het_han_giay=HAN_MA_TAM_2FA)
        # Đặt trong #fragment: không bị gửi lên máy chủ, không lưu vào nhật ký truy cập
        return ket_thuc(_chuyen(f"login.html?tiep={quote(tam['tiep'])}#ma_tam={ma_tam}"))
    resp = _chuyen(tam["tiep"])
    _mo_phien(db, user, request, resp, bool(tam.get("ghi_nho")), hai_lop=False)
    logbus.ghi("INFO", "auth", "dang_nhap_mxh", f"Đăng nhập bằng {ten_ncc}", nguoi_dung=user.email, ip=ip_cua(request))
    return ket_thuc(resp)


def _them_lien_ket(db, uid: int, hs: oauth.HoSo):
    db.execute(text("""
        INSERT INTO lien_ket_mxh (nguoi_dung_id, nha_cung_cap, ma_ngoai, email, ho_ten)
        VALUES (:u, :n, :m, :e, :t) ON CONFLICT (nha_cung_cap, ma_ngoai) DO NOTHING
    """), {"u": uid, "n": hs.nha_cung_cap, "m": hs.ma, "e": hs.email, "t": (hs.ho_ten or "")[:255]})
    db.commit()


@router.get("/lien-ket")
def ds_lien_ket(user: models.NguoiDung = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(text("SELECT nha_cung_cap, email, ho_ten, tao_luc, dang_nhap_cuoi FROM lien_ket_mxh WHERE nguoi_dung_id = :u"),
                      {"u": user.id}).fetchall()
    return {"co_mat_khau": bool(user.co_mat_khau), "da_cau_hinh": oauth.ds_da_cau_hinh(),
            "lien_ket": [{"nha_cung_cap": r.nha_cung_cap, "email": r.email, "ho_ten": r.ho_ten, "tao_luc": r.tao_luc.isoformat(),
                          "dang_nhap_cuoi": r.dang_nhap_cuoi.isoformat() if r.dang_nhap_cuoi else None} for r in rows]}


@router.delete("/{ncc}")
def go_lien_ket(ncc: str, request: Request, user: models.NguoiDung = Depends(get_current_user), db: Session = Depends(get_db)):
    so = db.execute(text("SELECT count(*) FROM lien_ket_mxh WHERE nguoi_dung_id = :u"), {"u": user.id}).scalar()
    if not user.co_mat_khau and so <= 1:
        raise HTTPException(400, "Đây là cách đăng nhập duy nhất của tài khoản. Hãy đặt mật khẩu trước khi gỡ liên kết")
    r = db.execute(text("DELETE FROM lien_ket_mxh WHERE nguoi_dung_id = :u AND nha_cung_cap = :n"), {"u": user.id, "n": ncc})
    db.commit()
    if not r.rowcount:
        raise HTTPException(404, "Chưa liên kết nhà cung cấp này")
    logbus.ghi("WARN", "auth", "go_lien_ket_mxh", f"Gỡ liên kết {ncc}", nguoi_dung=user.email, ip=ip_cua(request))
    return {"message": "Đã gỡ liên kết"}
