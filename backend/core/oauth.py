"""Đăng nhập / đăng ký bằng Google, Facebook, Zalo — OAuth 2.0 Authorization Code + PKCE (RFC 7636).

Mỗi nhà cung cấp chỉ bật khi có khóa ứng dụng trong .env (xem docs/DANG_NHAP_MXH.md):
  GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET       — Google Cloud Console → OAuth client (Web application)
  FACEBOOK_APP_ID  / FACEBOOK_APP_SECRET        — developers.facebook.com → ứng dụng có sản phẩm Facebook Login
  ZALO_APP_ID      / ZALO_APP_SECRET            — developers.zalo.me → ứng dụng có Đăng nhập với Zalo
Địa chỉ chuyển hướng (khai báo y hệt ở trang nhà phát triển):  <địa chỉ web>/api/v1/auth/oauth/<google|facebook|zalo>/callback

Bảo mật:
- state ngẫu nhiên + code_verifier (PKCE) lưu trong cookie HttpOnly ký số, hiệu lực 10 phút → chống CSRF đăng nhập và đánh tráo mã.
- Chỉ dùng thông tin hồ sơ lấy trực tiếp từ máy chủ nhà cung cấp bằng access token (không tin dữ liệu trình duyệt gửi lên).
- Email chỉ được coi là đã xác minh khi nhà cung cấp khẳng định (Google: email_verified; Facebook chỉ trả email đã xác nhận);
  Zalo không cung cấp email.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass

import requests

HAN_STATE_GIAY = 600
TIMEOUT = 15
FB_PHIEN_BAN = os.getenv("FACEBOOK_GRAPH_VERSION", "v23.0")


@dataclass
class HoSo:
    """Thông tin người dùng chuẩn hóa từ nhà cung cấp."""
    nha_cung_cap: str
    ma: str                       # định danh duy nhất của người dùng tại nhà cung cấp (sub / id)
    ho_ten: str
    email: str | None
    email_da_xac_minh: bool
    anh: str | None = None


class LoiOAuth(Exception):
    """Lỗi hiển thị được cho người dùng."""


def _env(ten: str) -> str:
    """Đọc khóa từ biến môi trường; chưa có thì đọc thẳng tệp .env (thêm khóa vào .env không cần khởi động lại máy chủ)."""
    gt = (os.getenv(ten) or "").strip()
    if not gt:
        try:
            from pathlib import Path
            from dotenv import dotenv_values
            gt = (dotenv_values(Path(__file__).resolve().parents[2] / ".env").get(ten) or "").strip()
        except Exception:
            gt = ""
    return gt


NHA_CUNG_CAP = {
    "google": {"ten": "Google", "id": "GOOGLE_CLIENT_ID", "bi_mat": "GOOGLE_CLIENT_SECRET"},
    "facebook": {"ten": "Facebook", "id": "FACEBOOK_APP_ID", "bi_mat": "FACEBOOK_APP_SECRET"},
    "zalo": {"ten": "Zalo", "id": "ZALO_APP_ID", "bi_mat": "ZALO_APP_SECRET"},
}


def da_cau_hinh(ncc: str) -> bool:
    c = NHA_CUNG_CAP.get(ncc)
    return bool(c and _env(c["id"]) and _env(c["bi_mat"]))


def ds_da_cau_hinh() -> list[dict]:
    return [{"ma": k, "ten": v["ten"]} for k, v in NHA_CUNG_CAP.items() if da_cau_hinh(k)]


def tao_pkce() -> tuple[str, str]:
    """(code_verifier, code_challenge S256)."""
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


def url_uy_quyen(ncc: str, redirect_uri: str, state: str, challenge: str) -> str:
    from urllib.parse import urlencode
    if ncc == "google":
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
            "client_id": _env("GOOGLE_CLIENT_ID"), "redirect_uri": redirect_uri, "response_type": "code",
            "scope": "openid email profile", "state": state, "code_challenge": challenge,
            "code_challenge_method": "S256", "prompt": "select_account", "access_type": "online"})
    if ncc == "facebook":
        return f"https://www.facebook.com/{FB_PHIEN_BAN}/dialog/oauth?" + urlencode({
            "client_id": _env("FACEBOOK_APP_ID"), "redirect_uri": redirect_uri, "response_type": "code",
            "scope": "email,public_profile", "state": state, "code_challenge": challenge,
            "code_challenge_method": "S256"})
    if ncc == "zalo":
        return "https://oauth.zaloapp.com/v4/permission?" + urlencode({
            "app_id": _env("ZALO_APP_ID"), "redirect_uri": redirect_uri, "state": state,
            "code_challenge": challenge})
    raise LoiOAuth("Nhà cung cấp không được hỗ trợ")


def _json(r: requests.Response, buoc: str) -> dict:
    try:
        d = r.json()
    except ValueError:
        d = {}
    if r.status_code >= 400 or not isinstance(d, dict) or d.get("error"):
        loi = d.get("error_description") or d.get("error_name") or d.get("message") or \
            (d.get("error") if isinstance(d.get("error"), str) else (d.get("error") or {}).get("message")) or r.status_code
        raise LoiOAuth(f"{buoc} thất bại ({loi})")
    return d


def doi_ma_lay_ho_so(ncc: str, code: str, verifier: str, redirect_uri: str) -> HoSo:
    """Đổi authorization code lấy access token rồi đọc hồ sơ người dùng từ máy chủ nhà cung cấp."""
    if ncc == "google":
        tk = _json(requests.post("https://oauth2.googleapis.com/token", timeout=TIMEOUT, data={
            "code": code, "client_id": _env("GOOGLE_CLIENT_ID"), "client_secret": _env("GOOGLE_CLIENT_SECRET"),
            "redirect_uri": redirect_uri, "grant_type": "authorization_code", "code_verifier": verifier}), "Đổi mã Google")
        u = _json(requests.get("https://openidconnect.googleapis.com/v1/userinfo", timeout=TIMEOUT,
                               headers={"Authorization": f"Bearer {tk['access_token']}"}), "Đọc hồ sơ Google")
        return HoSo("google", str(u["sub"]), u.get("name") or (u.get("email") or "").split("@")[0],
                    (u.get("email") or "").lower() or None, bool(u.get("email_verified")), u.get("picture"))
    if ncc == "facebook":
        tk = _json(requests.get(f"https://graph.facebook.com/{FB_PHIEN_BAN}/oauth/access_token", timeout=TIMEOUT, params={
            "client_id": _env("FACEBOOK_APP_ID"), "client_secret": _env("FACEBOOK_APP_SECRET"),
            "redirect_uri": redirect_uri, "code": code, "code_verifier": verifier}), "Đổi mã Facebook")
        # appsecret_proof: chứng minh lời gọi đến từ máy chủ có app secret (khuyến nghị bảo mật của Meta)
        proof = hmac.new(_env("FACEBOOK_APP_SECRET").encode(), tk["access_token"].encode(), hashlib.sha256).hexdigest()
        u = _json(requests.get(f"https://graph.facebook.com/{FB_PHIEN_BAN}/me", timeout=TIMEOUT, params={
            "fields": "id,name,email,picture.type(large)", "access_token": tk["access_token"], "appsecret_proof": proof}),
            "Đọc hồ sơ Facebook")
        email = (u.get("email") or "").lower() or None
        return HoSo("facebook", str(u["id"]), u.get("name") or "Người dùng Facebook", email, email is not None,
                    ((u.get("picture") or {}).get("data") or {}).get("url"))
    if ncc == "zalo":
        tk = _json(requests.post("https://oauth.zaloapp.com/v4/access_token", timeout=TIMEOUT,
                                 headers={"secret_key": _env("ZALO_APP_SECRET")}, data={
            "code": code, "app_id": _env("ZALO_APP_ID"), "grant_type": "authorization_code", "code_verifier": verifier}),
            "Đổi mã Zalo")
        u = _json(requests.get("https://graph.zalo.me/v2.0/me", timeout=TIMEOUT, params={"fields": "id,name,picture"},
                               headers={"access_token": tk["access_token"]}), "Đọc hồ sơ Zalo")
        return HoSo("zalo", str(u["id"]), u.get("name") or "Người dùng Zalo", None, False,
                    ((u.get("picture") or {}).get("data") or {}).get("url"))
    raise LoiOAuth("Nhà cung cấp không được hỗ trợ")
