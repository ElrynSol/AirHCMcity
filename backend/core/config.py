"""Cấu hình chung: nạp .env, đường dẫn dự án, CORS, cookie."""

import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True))
except ImportError:
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
for _thu_muc in ('ml', 'data_pipeline'):  # module dùng chung: predict, train_model, tinh_aqi, download_gee_data...
    _d = str(PROJECT_ROOT / _thu_muc)
    if _d not in sys.path:
        sys.path.insert(0, _d)

# CORS: khi dùng cookie kèm credentials thì KHÔNG được để "*", phải liệt kê đúng miền được phép.
# Có thể thêm miền khác trong .env: CORS_ORIGINS=http://localhost:5500,https://ten-mien-cua-ban
CORS_ORIGINS = [o.strip() for o in os.getenv(
    "CORS_ORIGINS",
    "http://localhost:8000,http://127.0.0.1:8000,http://localhost:5500,http://127.0.0.1:5500"
).split(",") if o.strip()]

COOKIE_NAME = "access_token"

# development (mặc định, máy cá nhân) | production (máy chủ công khai: tắt /docs, bắt buộc HTTPS cookie...)
MOI_TRUONG = os.getenv("MOI_TRUONG", "development").strip().lower()
# Địa chỉ công khai của web (dùng cho SEO: sitemap, thẻ canonical). Vd: https://airhcm.duckdns.org
DIA_CHI_CONG_KHAI = os.getenv("DIA_CHI_CONG_KHAI", "").strip().rstrip("/")
COOKIE_MAX_AGE = int(os.getenv("COOKIE_MAX_AGE", str(8 * 3600)))  # 8 giờ
