"""SEO: máy chủ tự chèn thẻ tối ưu tìm kiếm vào mọi trang HTML khi phục vụ (không phải sửa tay 18 trang).

- <link rel="canonical">, Open Graph + Twitter Card (xem trước đẹp khi chia sẻ Facebook/Zalo/Messenger)
- robots: trang công khai cho Google lập chỉ mục; trang đăng nhập/quản trị/tài khoản thì "noindex"
- Dữ liệu có cấu trúc JSON-LD (schema.org WebSite + Dataset) ở trang chủ
- Tiêu đề thống nhất "… · AirHCM"; mã xác minh Google Search Console (GOOGLE_SITE_VERIFICATION trong .env)
- /robots.txt và /sitemap.xml sinh tự động theo địa chỉ công khai (DIA_CHI_CONG_KHAI)
"""

import html
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from starlette.responses import FileResponse, HTMLResponse
from starlette.staticfiles import StaticFiles

from core import config

TEN = "AirHCM"
MO_TA_CHUNG = ("Giám sát và dự báo chất lượng không khí TP.HCM theo VN_AQI (QĐ 1459/QĐ-TCMT): bản đồ AQI, "
               "dự báo PM2.5 24 giờ, cảnh báo ô nhiễm, dữ liệu vệ tinh Sentinel-5P.")
# Trang riêng tư / quản trị: không cho máy tìm kiếm lập chỉ mục
KHONG_INDEX = {"login.html", "tai-khoan.html", "nhat-ky.html", "luong-canh-bao.html", "tram.html", "trang-thai-du-lieu.html"}
# Trang đưa vào sitemap: (tệp, độ ưu tiên, tần suất thay đổi)
SITEMAP = [("tong-quan.html", "1.0", "hourly"), ("index.html", "0.9", "hourly"), ("du-bao.html", "0.9", "hourly"),
           ("ban-do-nhiet.html", "0.7", "daily"), ("canh-bao.html", "0.7", "hourly"), ("thong-ke.html", "0.6", "daily"),
           ("so-sanh.html", "0.6", "daily"), ("kich-ban.html", "0.5", "weekly"), ("hoa-gio.html", "0.5", "daily"),
           ("bao-cao.html", "0.4", "weekly"), ("phuong-phap.html", "0.6", "monthly"), ("gioi-thieu.html", "0.5", "monthly"),
           ("chinh-sach-rieng-tu.html", "0.3", "yearly"),
           ("phan-anh.html", "0.6", "hourly"),
           ("tai-app.html", "0.5", "monthly"),
           ("tra-cuu-khong-gian.html", "0.6", "monthly")]


def goc_cong_khai(scope) -> str:
    """https://ten-mien (ưu tiên DIA_CHI_CONG_KHAI; không có thì suy ra từ yêu cầu hiện tại)."""
    if config.DIA_CHI_CONG_KHAI:
        return config.DIA_CHI_CONG_KHAI
    host = dict(scope.get("headers") or []).get(b"host", b"localhost:8000").decode()
    return f"{scope.get('scheme', 'http')}://{host}"


def _the_seo(trang: str, noi_dung: str, goc: str) -> str:
    m = re.search(r"<title>(.*?)</title>", noi_dung, re.S | re.I)
    tieu_de = html.unescape(m.group(1).strip()) if m else TEN
    m = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', noi_dung, re.I)
    mo_ta = html.unescape(m.group(1)) if m else MO_TA_CHUNG
    url = f"{goc}/{trang}"
    anh = f"{goc}/icons/icon-512.png"
    e = lambda s: html.escape(s, quote=True)
    the = []
    if not re.search(r'rel="canonical"', noi_dung, re.I):
        the.append(f'<link rel="canonical" href="{e(url)}">')
    if not re.search(r'name="robots"', noi_dung, re.I):
        the.append('<meta name="robots" content="' + ("noindex, nofollow" if trang in KHONG_INDEX else "index, follow, max-image-preview:large") + '">')
    if not re.search(r'property="og:', noi_dung, re.I):
        the += [f'<meta property="og:type" content="website">', f'<meta property="og:site_name" content="{TEN}">',
                f'<meta property="og:locale" content="vi_VN">', f'<meta property="og:title" content="{e(tieu_de)}">',
                f'<meta property="og:description" content="{e(mo_ta)}">', f'<meta property="og:url" content="{e(url)}">',
                f'<meta property="og:image" content="{e(anh)}">', '<meta property="og:image:width" content="512">',
                '<meta property="og:image:height" content="512">', '<meta name="twitter:card" content="summary">',
                f'<meta name="twitter:title" content="{e(tieu_de)}">', f'<meta name="twitter:description" content="{e(mo_ta)}">']
    xm = os.getenv("GOOGLE_SITE_VERIFICATION", "").strip()
    if xm:
        the.append(f'<meta name="google-site-verification" content="{e(xm)}">')
    if trang == "tong-quan.html":
        ld = [{"@context": "https://schema.org", "@type": "WebSite", "name": TEN, "url": goc + "/", "inLanguage": "vi",
               "description": MO_TA_CHUNG},
              {"@context": "https://schema.org", "@type": "Dataset",
               "name": "Chất lượng không khí TP.HCM theo giờ (PM2.5, PM10, O3, VN_AQI)",
               "description": "Số liệu PM2.5, PM10, O3 theo giờ (mô hình CAMS qua Open-Meteo), cột khí NO2/CO/SO2 vệ tinh Sentinel-5P "
                              "và chỉ số VN_AQI tính theo QĐ 1459/QĐ-TCMT cho các trạm tại TP.HCM; kèm dự báo PM2.5 24 giờ.",
               "url": goc + "/tong-quan.html", "inLanguage": "vi", "isAccessibleForFree": True,
               "spatialCoverage": {"@type": "Place", "name": "Thành phố Hồ Chí Minh, Việt Nam",
                                   "geo": {"@type": "GeoCoordinates", "latitude": 10.7769, "longitude": 106.7009}},
               "temporalCoverage": "2022-08-01/..", "creator": {"@type": "Person", "name": "Lê Ngọc Ánh Dương"},
               "variableMeasured": ["PM2.5", "PM10", "O3", "NO2", "CO", "SO2", "VN_AQI"]}]
        the.append('<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False).replace("</", "<\\/") + "</script>")
    return "\n".join(the)


def chen_seo(trang: str, noi_dung: str, goc: str) -> str:
    # Tiêu đề thống nhất có tên thương hiệu (Google hiển thị tiêu đề này trong kết quả tìm kiếm)
    noi_dung = re.sub(r"<title>((?:(?!AirHCM).)*?)</title>", lambda m: f"<title>{m.group(1).strip()} · {TEN}</title>",
                      noi_dung, count=1, flags=re.S | re.I)
    them = _the_seo(trang, noi_dung, goc)
    return noi_dung.replace("</head>", them + "\n</head>", 1) if them and "</head>" in noi_dung else noi_dung


class WebTinh(StaticFiles):
    """StaticFiles của Starlette + chèn thẻ SEO vào trang HTML."""

    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        if isinstance(resp, FileResponse) and resp.status_code == 200 and str(resp.path).endswith(".html"):
            f = Path(resp.path)
            noi_dung = chen_seo(f.name, f.read_text(encoding="utf-8"), goc_cong_khai(scope))
            # no-cache: trình duyệt luôn hỏi lại bản mới (trang nhỏ, service worker vẫn cho chạy offline)
            return HTMLResponse(noi_dung, headers={"Cache-Control": "no-cache"})
        return resp


def robots_txt(goc: str) -> str:
    cam = "\n".join(f"Disallow: /{t}" for t in sorted(KHONG_INDEX))
    return f"User-agent: *\nAllow: /\nDisallow: /api/\n{cam}\n\nSitemap: {goc}/sitemap.xml\n"


def sitemap_xml(goc: str) -> str:
    fe = config.PROJECT_ROOT / "frontend"
    dong = []
    for tep, uu_tien, tan_suat in SITEMAP:
        p = fe / tep
        if not p.exists():
            continue
        lastmod = datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d")
        dong.append(f"  <url><loc>{html.escape(goc)}/{tep}</loc><lastmod>{lastmod}</lastmod>"
                    f"<changefreq>{tan_suat}</changefreq><priority>{uu_tien}</priority></url>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(dong) + "\n</urlset>\n")
