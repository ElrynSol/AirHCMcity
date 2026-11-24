"""Seed các điểm dữ liệu mẫu vào CSDL (đọc thông tin đăng nhập admin từ biến môi trường hoặc nhập tay)."""

import getpass
import os
import sys
import requests
from core import config  # noqa: F401  (nạp .env)

BASE_URL = os.getenv("SEED_API_URL", "http://127.0.0.1:8000/api/v1").rstrip("/")
email = (os.getenv("SEED_ADMIN_EMAIL") or "").strip() or input("Email quản trị: ").strip()
mat_khau = os.getenv("SEED_ADMIN_PASSWORD") or getpass.getpass("Mật khẩu quản trị: ")

session = requests.Session()
login_resp = session.post(f"{BASE_URL}/auth/login", json={"email": email, "mat_khau": mat_khau}, timeout=15)
if login_resp.status_code != 200:
    print(f"Đăng nhập thất bại ({login_resp.status_code}): {login_resp.text}")
    sys.exit(1)

stations = [
    # --- Khu vực TP.HCM cũ (theo tên phường mới sau sáp nhập) ---
    {"ma_tram": "T01", "ten_tram": "Phường Sài Gòn", "vi_do": 10.7769, "kinh_do": 106.7009},
    {"ma_tram": "T02", "ten_tram": "Phường Chợ Lớn (Quận 5 cũ)", "vi_do": 10.7539, "kinh_do": 106.6633},
    {"ma_tram": "T03", "ten_tram": "Phường Gia Định (Bình Thạnh cũ)", "vi_do": 10.8014, "kinh_do": 106.7109},
    {"ma_tram": "T04", "ten_tram": "Khu vực Quận 7 - Phú Mỹ Hưng", "vi_do": 10.7325, "kinh_do": 106.7144},
    {"ma_tram": "T05", "ten_tram": "Khu vực Tân Bình - Sân bay Tân Sơn Nhất", "vi_do": 10.8188, "kinh_do": 106.6520},
    {"ma_tram": "T06", "ten_tram": "Khu vực Thủ Đức - Khu Công nghệ cao", "vi_do": 10.8508, "kinh_do": 106.7891},
    {"ma_tram": "T07", "ten_tram": "Khu vực Bình Tân - An Lạc", "vi_do": 10.7379, "kinh_do": 106.5991},

    # --- Khu vực Bình Dương cũ (nay thuộc TP.HCM) ---
    {"ma_tram": "T08", "ten_tram": "Phường Bình Dương (Thủ Dầu Một cũ)", "vi_do": 10.9804, "kinh_do": 106.6519},
    {"ma_tram": "T09", "ten_tram": "Khu vực Dĩ An - Khu công nghiệp", "vi_do": 10.9089, "kinh_do": 106.7717},
    {"ma_tram": "T10", "ten_tram": "Khu vực Thuận An", "vi_do": 10.9158, "kinh_do": 106.7014},

    # --- Khu vực Bà Rịa - Vũng Tàu cũ (nay thuộc TP.HCM) ---
    {"ma_tram": "T11", "ten_tram": "Phường Vũng Tàu (TP. Vũng Tàu cũ)", "vi_do": 10.3460, "kinh_do": 107.0843},
    {"ma_tram": "T12", "ten_tram": "Khu vực Bà Rịa - Trung tâm hành chính cũ", "vi_do": 10.4956, "kinh_do": 107.1686},
]

for s in stations:
    s["trang_thai"] = "Hoat Dong"
    resp = session.post(f"{BASE_URL}/tram", json=s, timeout=15)
    if resp.status_code == 200:
        print(f"[OK] Đã tạo: {s['ten_tram']}")
    else:
        print(f"[LOI] {s['ten_tram']}: {resp.text}")

print("\nHoàn tất seed dữ liệu điểm!")