"""Kiểm thử các lớp bảo mật đăng nhập chuẩn doanh nghiệp (không cần CSDL). Chạy từ backend/: python -m pytest ../tests -q"""
import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))


@pytest.fixture
def auth(monkeypatch):
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("JWT_SECRET_KEY", "k" * 48)
    sys.modules.pop("auth", None)
    return importlib.import_module("auth")


# ---------------------------------------------------------------- Mật khẩu
def test_chinh_sach_mat_khau():
    from core.mat_khau import kiem_tra_mat_khau as kt
    assert kt("ngan1") and "10 ký tự" in kt("ngan1")
    assert kt("chiconchucai") and "chữ số" in kt("chiconchucai")
    assert kt("12345678901") and "chữ" in kt("12345678901")
    assert kt("password123") and "phổ biến" in kt("password123")          # danh sách mật khẩu phổ biến
    assert kt("Matkhau123!") and "phổ biến" in kt("Matkhau123!")          # biến thể có hậu tố số/ký tự
    assert kt("aaaaaaaaaa1") and "lặp" in kt("aaaaaaaaaa1")
    assert kt("nguyenvana2026", email="nguyenvana@gmail.com") and "email" in kt("nguyenvana2026", email="nguyenvana@gmail.com")
    assert kt("Duong-Khong-Khi-9", ho_ten="Lê Ánh Dương") and "họ tên" in kt("Duong-Khong-Khi-9", ho_ten="Lê Ánh Dương")
    assert kt("x1" * 70) and "tối đa" in kt("x1" * 70)
    assert kt("Bui-Min-Sai-Gon-2026") is None
    assert kt("trời xanh mây trắng 7") is None                             # cụm từ tiếng Việt có dấu


def test_argon2_va_nang_cap_tu_bcrypt(auth):
    h = auth.hash_password("Khong-Khi-Sach-2026")
    assert h.startswith("$argon2id$")
    assert auth.verify_password("Khong-Khi-Sach-2026", h) and not auth.verify_password("sai", h)
    assert not auth.can_bam_lai(h)
    import bcrypt
    cu = bcrypt.hashpw(b"Mat-Khau-Cu-2024", bcrypt.gensalt(rounds=4)).decode()
    assert auth.verify_password("Mat-Khau-Cu-2024", cu)                   # hash bcrypt cũ vẫn đăng nhập được
    assert auth.can_bam_lai(cu)                                            # và được đánh dấu cần băm lại bằng Argon2id
    assert auth.verify_password("x", "khong-phai-hash") is False           # hash hỏng không làm sập máy chủ
    assert auth.verify_password_gia("bat-ky") is False


def test_token_phan_loai(auth):
    phien = auth.create_access_token({"sub": "a@b.vn", "sid": "s", "typ": "phien"})
    tam = auth.create_access_token({"sub": "a@b.vn", "typ": "2fa"}, het_han_giay=300)
    assert auth.decode_access_token(phien, loai="phien")["sid"] == "s"
    assert auth.decode_access_token(tam, loai="phien") is None             # mã tạm 2FA không dùng làm phiên được
    assert auth.decode_access_token(phien, loai="2fa") is None
    p = auth.decode_access_token(phien)
    assert {"iat", "exp", "jti", "iss"} <= set(p) and p["iss"] == "airhcm"
    assert auth.decode_access_token(auth.create_access_token({"sub": "x"}, het_han_giay=-5)) is None   # hết hạn


# ---------------------------------------------------------------- Chống dò mật khẩu
def test_khoa_theo_email_tren_nhieu_ip():
    from core import ratelimit as rl
    e = "phantan@test.vn"
    t0 = 1_000_000.0
    for i in range(rl.TOI_DA_THEO_EMAIL):                                  # mỗi IP chỉ sai 1 lần → không IP nào bị khóa riêng
        rl.ghi_that_bai(e, f"10.0.0.{i}", now=t0)
    assert rl.con_lai_giay(e, "10.9.9.9", now=t0 + 1) > 0                  # nhưng email bị khóa trên mọi IP
    assert rl.con_lai_giay(e, "10.9.9.9", now=t0 + rl.CUA_SO_GIAY + 1) == 0


def test_bo_dem_chung():
    from core import ratelimit as rl
    for _ in range(3):
        assert rl.vuot_gioi_han("thu", "1.1.1.1", 3, 60, now=500.0) == 0
    assert rl.vuot_gioi_han("thu", "1.1.1.1", 3, 60, now=501.0) > 0
    assert rl.vuot_gioi_han("thu", "2.2.2.2", 3, 60, now=501.0) == 0       # IP khác không ảnh hưởng
    assert rl.vuot_gioi_han("thu", "1.1.1.1", 3, 60, now=561.0) == 0       # hết cửa sổ thời gian


# ---------------------------------------------------------------- Xác thực 2 lớp
def test_totp_dung_sai_va_chong_dung_lai(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "k" * 48)
    from core import phien
    import pyotp
    bm = phien.tao_bi_mat_totp()
    t = pyotp.TOTP(bm)
    buoc = phien.kiem_tra_totp(bm, t.now(), None)
    assert buoc is not None
    assert phien.kiem_tra_totp(bm, t.now(), buoc) is None                  # cùng mã dùng lần 2 bị từ chối (replay)
    assert phien.kiem_tra_totp(bm, "000000" if t.now() != "000000" else "111111", None) is None
    assert phien.kiem_tra_totp(bm, "12ab56", None) is None
    assert phien.giai_ma_bi_mat(phien.ma_hoa_bi_mat(bm)) == bm             # bí mật lưu dạng mã hóa
    assert phien.ma_hoa_bi_mat(bm) != bm
    assert phien.giai_ma_bi_mat("rac") is None
    assert phien.uri_totp(bm, "a@b.vn").startswith("otpauth://totp/AirHCM:a%40b.vn")
    assert "<svg" in phien.qr_svg("otpauth://totp/x")


def test_ma_du_phong_dung_mot_lan():
    from core import phien
    ds, json_bam = phien.tao_ma_du_phong()
    assert len(ds) == 8 and len(set(ds)) == 8 and all(len(m) == 9 and m[4] == "-" for m in ds)
    assert ds[0] not in json_bam                                           # chỉ lưu bản băm
    con = phien.dung_ma_du_phong(json_bam, ds[0].upper())                  # không phân biệt hoa/thường
    assert con is not None and len(json.loads(con)) == 7
    assert phien.dung_ma_du_phong(con, ds[0]) is None                      # mã đã dùng không dùng lại được
    assert phien.dung_ma_du_phong(json_bam, "sai1-sai2") is None


# ---------------------------------------------------------------- SEO + header bảo mật
def test_chen_seo():
    from core import seo
    trang = '<html><head><meta name="description" content="Mô tả & thử"><title>Dự báo</title></head><body></body></html>'
    kq = seo.chen_seo("du-bao.html", trang, "https://airhcm.vn")
    assert "<title>Dự báo · AirHCM</title>" in kq
    assert '<link rel="canonical" href="https://airhcm.vn/du-bao.html">' in kq
    assert 'content="index, follow' in kq and 'property="og:description" content="Mô tả &amp; thử"' in kq
    assert 'content="noindex, nofollow"' in seo.chen_seo("login.html", trang, "https://airhcm.vn")
    tq = seo.chen_seo("tong-quan.html", trang, "https://airhcm.vn")
    ld = json.loads(tq.split('application/ld+json">')[1].split("</script>")[0])
    assert [x["@type"] for x in ld] == ["WebSite", "Dataset"]
    assert seo.chen_seo("du-bao.html", kq, "https://airhcm.vn").count("canonical") == 1   # không chèn lặp
    assert "Disallow: /login.html" in seo.robots_txt("https://airhcm.vn") and "Sitemap: https://airhcm.vn/sitemap.xml" in seo.robots_txt("https://airhcm.vn")
    assert "<loc>https://airhcm.vn/tong-quan.html</loc>" in seo.sitemap_xml("https://airhcm.vn")


def test_oauth_url_pkce_va_ho_so(monkeypatch):
    """Đăng nhập Google/Facebook/Zalo: URL ủy quyền chuẩn, PKCE S256, đọc hồ sơ đúng (giả lập máy chủ nhà cung cấp)."""
    import base64
    import hashlib
    from urllib.parse import parse_qs, urlparse
    from core import oauth
    for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "FACEBOOK_APP_ID", "FACEBOOK_APP_SECRET", "ZALO_APP_ID", "ZALO_APP_SECRET"):
        monkeypatch.setenv(k, "x-" + k)
    assert [x["ma"] for x in oauth.ds_da_cau_hinh()] == ["google", "facebook", "zalo"]
    monkeypatch.delenv("ZALO_APP_SECRET")
    assert not oauth.da_cau_hinh("zalo")                                   # thiếu khóa → không hiện nút
    v, ch = oauth.tao_pkce()
    assert 43 <= len(v) <= 128 and ch == base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).decode().rstrip("=")
    q = parse_qs(urlparse(oauth.url_uy_quyen("google", "https://a.vn/cb", "st", ch)).query)
    assert q["code_challenge_method"] == ["S256"] and q["state"] == ["st"] and "openid" in q["scope"][0]

    class R:
        def __init__(self, d, st=200): self._d, self.status_code = d, st
        def json(self): return self._d
    monkeypatch.setattr(oauth.requests, "post", lambda *a, **k: R({"access_token": "t"}))
    monkeypatch.setattr(oauth.requests, "get", lambda *a, **k: R({"sub": "123", "email": "A@Gmail.com", "email_verified": False, "name": "A"}))
    hs = oauth.doi_ma_lay_ho_so("google", "c", v, "https://a.vn/cb")
    assert (hs.ma, hs.email, hs.email_da_xac_minh) == ("123", "a@gmail.com", False)   # email chưa xác minh được đánh dấu rõ
    monkeypatch.setattr(oauth.requests, "post", lambda *a, **k: R({"error": "invalid_grant", "error_description": "Bad"}, 400))
    with pytest.raises(oauth.LoiOAuth):
        oauth.doi_ma_lay_ho_so("google", "c", v, "https://a.vn/cb")


def test_oauth_chi_chuyen_ve_trang_noi_bo():
    from routers.oauth import _trang_tiep
    assert _trang_tiep("du-bao.html?x=1") == "du-bao.html?x=1"
    for xau in ("https://ke-xau.com", "//ke-xau.com", "javascript:alert(1)", "login.html", "../a.html", None, 'a.html"><script>'):
        assert _trang_tiep(xau) == "tong-quan.html"


def test_phan_anh_kiem_tra_du_lieu():
    """Phản ánh ô nhiễm của người dân: loại hợp lệ, tọa độ trong vùng TP.HCM, mô tả được làm sạch và giới hạn độ dài."""
    from services import phan_anh as pa
    d = pa.chuan_hoa("dot_rac", "  Khói   đen\n\n bốc lên  ", "10.7769", 106.7009)
    assert d == {"loai": "dot_rac", "mo_ta": "Khói đen bốc lên", "vi_do": 10.7769, "kinh_do": 106.7009}
    assert pa.chuan_hoa("khoi", "", 10.8, 106.7)["mo_ta"] is None
    for sai in (("loai_la", "x", 10.8, 106.7),            # loại không có trong danh mục
                ("khoi", "x", 21.03, 105.85),              # Hà Nội: ngoài vùng theo dõi
                ("khoi", "x", "abc", 106.7),               # tọa độ không phải số
                ("khoi", "x" * 501, 10.8, 106.7),          # mô tả quá dài
                ("khac", "ngắn", 10.8, 106.7)):            # loại "Khác" phải mô tả đủ rõ
        with pytest.raises(ValueError):
            pa.chuan_hoa(*sai)
    with pytest.raises(ValueError):
        pa.duyet(1, "trang_thai_la", 1)                    # trạng thái duyệt không hợp lệ bị chặn trước khi chạm CSDL


def test_header_bao_mat_va_csrf():
    from starlette.applications import Starlette
    from starlette.responses import HTMLResponse, JSONResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient
    from core.bao_mat_http import BaoMatHTTP

    app = Starlette(routes=[Route("/", lambda r: HTMLResponse("<p>x</p>")),
                            Route("/api/v1/x", lambda r: JSONResponse({"ok": 1}), methods=["POST"])])
    app.add_middleware(BaoMatHTTP)
    c = TestClient(app, base_url="http://testserver")
    h = c.get("/").headers
    assert h["x-frame-options"] == "DENY" and h["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in h["content-security-policy"]
    c.cookies.set("access_token", "t")
    assert c.post("/api/v1/x", headers={"Origin": "https://ke-xau.example"}).status_code == 403   # CSRF bị chặn
    assert c.post("/api/v1/x", headers={"Origin": "http://testserver"}).status_code == 200        # cùng nguồn
    assert c.post("/api/v1/x").status_code == 200                                                   # không có Origin (công cụ, app)


def test_quet_khong_gian_kiem_tra_vung():
    """Tra cứu không gian: vùng tròn/khung/đa giác hợp lệ; chặn tọa độ ngoài TP.HCM, bán kính sai, đa giác thiếu điểm."""
    import json as _json
    from services import khong_gian as kg
    gj, tt = kg.tao_vung({"kieu": "tron", "tam": {"lat": 10.7769, "lon": 106.7009}, "ban_kinh_m": 3000})
    assert _json.loads(gj) == {"type": "Point", "coordinates": [106.7009, 10.7769]} and tt["ban_kinh_m"] == 3000
    gj, tt = kg.tao_vung({"kieu": "khung", "dinh": [{"lat": 10.80, "lon": 106.75}, {"lat": 10.75, "lon": 106.65}]})
    vong = _json.loads(gj)["coordinates"][0]
    assert len(vong) == 5 and vong[0] == vong[-1] and {tuple(p) for p in vong} >= {(106.65, 10.75), (106.75, 10.80)}   # 2 góc → 4 góc, khép kín
    gj, tt = kg.tao_vung({"kieu": "da_giac", "dinh": [{"lat": 10.75, "lon": 106.65}, {"lat": 10.80, "lon": 106.70}, {"lat": 10.75, "lon": 106.75}]})
    assert tt["so_dinh"] == 3 and len(_json.loads(gj)["coordinates"][0]) == 4
    for sai in ({"kieu": "tron", "tam": {"lat": 21.03, "lon": 105.85}, "ban_kinh_m": 1000},          # Hà Nội
                {"kieu": "tron", "tam": {"lat": 10.77, "lon": 106.70}, "ban_kinh_m": 10},              # bán kính quá nhỏ
                {"kieu": "tron", "tam": {"lat": 10.77, "lon": 106.70}, "ban_kinh_m": 999999},          # quá lớn
                {"kieu": "da_giac", "dinh": [{"lat": 10.75, "lon": 106.65}, {"lat": 10.80, "lon": 106.70}]},   # thiếu điểm
                {"kieu": "khung", "dinh": [{"lat": 10.75, "lon": 106.65}, {"lat": 10.75, "lon": 106.65}]},     # 2 góc trùng
                {"kieu": "tam_giac"}):
        with pytest.raises(kg.LoiHinhHoc):
            kg.tao_vung(sai)
