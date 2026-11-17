"""Kết nối PostgreSQL/PostGIS cho backend FastAPI.

Cấu hình (theo thứ tự ưu tiên):
1. DATABASE_URL=postgresql://user:matkhau@host:5432/ten_csdl   (Docker, máy chủ đám mây)
2. DB_USER, DB_PASS, DB_HOST, DB_PORT, DB_NAME                    (máy cá nhân, file .env)
"""

import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Tìm .env ở thư mục gốc dự án (lùi lên nếu file đang ở backend/)
env_path = Path(__file__).resolve().parent
for _ in range(3):
    if (env_path / ".env").exists():
        load_dotenv(env_path / ".env")
        break
    env_path = env_path.parent


def _url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        return url.replace("postgres://", "postgresql://", 1)   # một số nhà cung cấp dùng tiền tố postgres://
    user = os.getenv("DB_USER", "postgres")
    mat_khau = quote_plus(os.getenv("DB_PASS", ""))           # mật khẩu có @ : / # vẫn đúng
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    ten = os.getenv("DB_NAME", "air_quality_db")
    return f"postgresql://{user}:{mat_khau}@{host}:{port}/{ten}"


SQLALCHEMY_DATABASE_URL = _url()

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,        # kiểm tra kết nối trước khi dùng: CSDL khởi động lại thì tự nối lại
    pool_recycle=1800,         # làm mới kết nối sau 30 phút (tránh tường lửa/NAT cắt kết nối rảnh)
    pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
    connect_args={"connect_timeout": 10, "application_name": "airhcm"},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
