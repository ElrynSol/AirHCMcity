"""Chuỗi kết nối CSDL dùng chung cho các script (data_pipeline/, ml/).

Ưu tiên DATABASE_URL (Docker, máy chủ đám mây); nếu không có thì ghép từ DB_USER/DB_PASS/DB_HOST/DB_PORT/DB_NAME
(file .env trên máy cá nhân). Mật khẩu được mã hóa URL nên chứa ký tự đặc biệt (@ : / #) vẫn đúng.
"""

import os
from pathlib import Path
from urllib.parse import quote_plus


def _nap_env():
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    d = Path(__file__).resolve().parent
    for _ in range(3):
        if (d / ".env").exists():
            load_dotenv(d / ".env")
            return
        d = d.parent


def db_url() -> str:
    _nap_env()
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        return url.replace("postgres://", "postgresql://", 1)
    return (f"postgresql://{os.getenv('DB_USER', 'postgres')}:{quote_plus(os.getenv('DB_PASS', ''))}"
            f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME', 'air_quality_db')}")


def get_engine():
    from sqlalchemy import create_engine
    return create_engine(db_url(), pool_pre_ping=True)
