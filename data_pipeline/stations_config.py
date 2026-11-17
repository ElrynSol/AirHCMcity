"""
Nguồn dữ liệu duy nhất (single source of truth) cho danh sách trạm quan trắc.
Mọi tool tải dữ liệu (GEE, Open-Meteo) đều đọc từ đây - không hardcode riêng lẻ.
"""

from sqlalchemy import create_engine, text

import os
from dotenv import load_dotenv

# Tìm .env ở thư mục gốc dự án (lùi lên nếu file đang ở backend/)
from pathlib import Path
env_path = Path(__file__).resolve().parent.parent
for _ in range(3):
    if (env_path / ".env").exists():
        load_dotenv(env_path / ".env")
        break
    env_path = env_path.parent

DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")


def get_engine():
    """Kết nối CSDL: ưu tiên DATABASE_URL, sau đó DB_* trong .env (db_url.py)."""
    from db_url import get_engine as _g
    return _g()


def get_active_stations():
    """
    Trả về danh sách trạm đang hoạt động từ CSDL, dạng:
    [{'id': 1, 'ma_tram': 'T01', 'ten_tram': '...', 'lat': 10.77, 'lon': 106.70}, ...]
    """
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT id, ma_tram, ten_tram, ST_Y(toado) as lat, ST_X(toado) as lon
            FROM tram_quan_trac
            WHERE trang_thai = 'Hoat Dong'
            ORDER BY id
        """))
        stations = [dict(row._mapping) for row in result]
    return stations


if __name__ == "__main__":
    # Test nhanh
    stations = get_active_stations()
    print(f"Tìm thấy {len(stations)} trạm đang hoạt động:")
    for s in stations:
        print(f"  {s['ma_tram']} - {s['ten_tram']} ({s['lat']:.4f}, {s['lon']:.4f})")