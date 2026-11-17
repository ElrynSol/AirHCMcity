"""
Phân cụm (Clustering) các trạm quan trắc theo mức độ ô nhiễm bằng K-Means.
Mục đích: nhóm các trạm có đặc trưng ô nhiễm tương đồng, phục vụ
trực quan hóa vùng ô nhiễm và hỗ trợ ra quyết định quản lý theo khu vực.
"""

import pandas as pd
import numpy as np
import joblib
from sqlalchemy import create_engine
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score

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


import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parent.parent / 'data_pipeline'))
from db_url import get_engine as _get_engine_chung  # noqa: E402


def get_engine():
    """Kết nối CSDL: ưu tiên DATABASE_URL, sau đó DB_* trong .env (data_pipeline/db_url.py)."""
    return _get_engine_chung()


def load_du_lieu_tram():
    """Lấy đặc trưng trung bình của từng trạm để phân cụm."""
    engine = get_engine()

    df = pd.read_sql("""
    SELECT
        t.id AS tram_id, t.ma_tram, t.ten_tram,
        ST_Y(t.toado) AS lat, ST_X(t.toado) AS lon,
        AVG(COALESCE(d.pm25_smoothed, d.pm25_mean)) AS pm25_tb,
        AVG(COALESCE(d.pm10_smoothed, d.pm10_mean)) AS pm10_tb,
        AVG(COALESCE(d.o3_smoothed, d.o3_mean)) AS o3_tb
    FROM tram_quan_trac t
    JOIN du_lieu_tram_mat_dat d ON t.id = d.tram_id
    WHERE d.ngay_do >= CURRENT_DATE - INTERVAL '90 days'
    GROUP BY t.id, t.ma_tram, t.ten_tram, t.toado
""", engine)

    ve_tinh = pd.read_sql("""
        SELECT tram_id, AVG(no2_mean) AS no2_tb, AVG(co_mean) AS co_tb, AVG(so2_mean) AS so2_tb
        FROM du_lieu_gee_tphcm
        WHERE ngay_do >= CURRENT_DATE - INTERVAL '90 days'
        GROUP BY tram_id
    """, engine)

    df = pd.merge(df, ve_tinh, on='tram_id', how='left')
    df = df.dropna(subset=['pm25_tb', 'pm10_tb', 'o3_tb'])

    print(f"[1] Dữ liệu {len(df)} trạm để phân cụm")
    return df


def phan_cum(df, so_cum=3):
    """Phân cụm các trạm theo đặc trưng ô nhiễm bằng K-Means."""
    features = ['pm25_tb', 'pm10_tb', 'o3_tb']
    X = df[features].fillna(df[features].mean())

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    kmeans = KMeans(n_clusters=so_cum, random_state=42, n_init=10)
    df['cum'] = kmeans.fit_predict(X_scaled)

    # Đánh giá chất lượng phân cụm
    score = silhouette_score(X_scaled, df['cum'])
    print(f"[2] Silhouette Score: {score:.3f} (càng gần 1 càng tốt, >0.3 là chấp nhận được)")

    # Đặt tên cụm theo mức PM2.5 trung bình (thấp -> cao)
    thu_tu_cum = df.groupby('cum')['pm25_tb'].mean().sort_values().index.tolist()
    ten_cum = {thu_tu_cum[0]: 'Ô nhiễm thấp', thu_tu_cum[-1]: 'Ô nhiễm cao'}
    if so_cum == 3:
        ten_cum[thu_tu_cum[1]] = 'Ô nhiễm trung bình'

    df['ten_cum'] = df['cum'].map(ten_cum)

    print("\n=== KẾT QUẢ PHÂN CỤM ===")
    for _, row in df.iterrows():
        print(f"{row['ma_tram']} ({row['ten_tram']}): Cụm '{row['ten_cum']}' - PM2.5 TB={row['pm25_tb']:.1f}")

    return df, kmeans, scaler, score


def save_ket_qua(df, kmeans, scaler, score):
    """Lưu model và kết quả phân cụm."""
    joblib.dump({'model': kmeans, 'scaler': scaler, 'silhouette_score': score},
                'models/kmeans_phan_cum.pkl')

    # Lưu kết quả vào DB để dùng cho frontend
    engine = get_engine()
    with engine.begin() as conn:
        from sqlalchemy import text
        conn.execute(text("""
            ALTER TABLE tram_quan_trac ADD COLUMN IF NOT EXISTS nhom_o_nhiem VARCHAR(50)
        """))
        for _, row in df.iterrows():
            conn.execute(text("""
                UPDATE tram_quan_trac SET nhom_o_nhiem = :nhom WHERE id = :tram_id
            """), {"nhom": row['ten_cum'], "tram_id": row['tram_id']})

    print(f"\n✅ Đã lưu model phân cụm và cập nhật CSDL.")


if __name__ == "__main__":
    df = load_du_lieu_tram()
    df, kmeans, scaler, score = phan_cum(df, so_cum=3)
    save_ket_qua(df, kmeans, scaler, score)
    print("\n🎉 HOÀN TẤT PHÂN CỤM K-MEANS!")