"""
Tool nạp dữ liệu từ file CSV (đã tải từ GEE) vào PostgreSQL/PostGIS.
Dùng bảng: du_lieu_gee_tphcm
"""

import pandas as pd
from sqlalchemy import create_engine, text
import argparse

# ============================================
# CẤU HÌNH KẾT NỐI DATABASE
# ============================================
import os
from pathlib import Path
from dotenv import load_dotenv

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


def load_csv_to_db(csv_file, khu_vuc="TP.HCM"):
    print(f"[1] Đang đọc file: {csv_file}")
    df = pd.read_csv(csv_file)

    # Chuẩn hóa tên cột cho khớp với bảng PostgreSQL
    df = df.rename(columns={
        'Date': 'ngay_do',
        'NO2_Mean': 'no2_mean',
        'CO_Mean': 'co_mean',
        'SO2_Mean': 'so2_mean'
    })

    df['ngay_do'] = pd.to_datetime(df['ngay_do']).dt.date
    df['khu_vuc'] = khu_vuc
    df = df.round(8)

    print(f"[2] Chuẩn bị nạp {len(df)} dòng vào bảng du_lieu_gee_tphcm...")

    engine = get_engine()

    inserted = 0
    skipped = 0

    with engine.begin() as conn:
        for _, row in df.iterrows():
            try:
                conn.execute(text("""
                    INSERT INTO du_lieu_gee_tphcm (ngay_do, khu_vuc, no2_mean, co_mean, so2_mean)
                    VALUES (:ngay_do, :khu_vuc, :no2_mean, :co_mean, :so2_mean)
                    ON CONFLICT (ngay_do, khu_vuc) DO UPDATE
                    SET no2_mean = EXCLUDED.no2_mean,
                        co_mean = EXCLUDED.co_mean,
                        so2_mean = EXCLUDED.so2_mean,
                        ngay_cap_nhat = CURRENT_TIMESTAMP
                """), {
                    'ngay_do': row['ngay_do'],
                    'khu_vuc': row['khu_vuc'],
                    'no2_mean': row['no2_mean'],
                    'co_mean': row['co_mean'],
                    'so2_mean': row['so2_mean']
                })
                inserted += 1
            except Exception as e:
                print(f"⚠️ Lỗi dòng {row['ngay_do']}: {e}")
                skipped += 1

    print(f"✅ HOÀN TẤT! Đã nạp/cập nhật {inserted} dòng, lỗi {skipped} dòng.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nạp dữ liệu CSV vào PostgreSQL")
    parser.add_argument('--file', type=str, required=True, help='Đường dẫn file CSV cần nạp')
    parser.add_argument('--khu-vuc', type=str, default='TP.HCM', help='Tên khu vực (mặc định: TP.HCM)')

    args = parser.parse_args()
    load_csv_to_db(args.file, args.khu_vuc)

def predict_multiple_days(so_ngay=5):
    """Dự báo PM2.5 cho nhiều ngày tới bằng cách lặp lại dự báo tuần tự."""
    model, metadata = load_model()
    engine = get_engine()

    gee = pd.read_sql("""
        SELECT ngay_do, AVG(no2_mean) as no2_mean, AVG(co_mean) as co_gee, AVG(so2_mean) as so2_gee
        FROM du_lieu_gee_tphcm GROUP BY ngay_do ORDER BY ngay_do DESC LIMIT 15
    """, engine)
    tram = pd.read_sql("""
        SELECT ngay_do, AVG(pm25_mean) as pm25_mean, AVG(o3_mean) as o3_mean,
               AVG(nhiet_do_mean) as nhiet_do_mean, AVG(do_am_mean) as do_am_mean,
               AVG(gio_toc_do_mean) as gio_toc_do_mean, AVG(mua_tong) as mua_tong
        FROM du_lieu_tram_mat_dat GROUP BY ngay_do ORDER BY ngay_do DESC LIMIT 15
    """, engine)

    gee['ngay_do'] = pd.to_datetime(gee['ngay_do'])
    tram['ngay_do'] = pd.to_datetime(tram['ngay_do'])
    df = pd.merge(gee, tram, on='ngay_do', how='inner').sort_values('ngay_do').reset_index(drop=True)
    df['so2_gee'] = df['so2_gee'].clip(lower=0)

    if len(df) < 8:
        return {"error": "Không đủ dữ liệu để dự báo nhiều ngày."}

    ket_qua = []
    for i in range(so_ngay):
        latest = df.iloc[-1]
        next_date = latest['ngay_do'] + pd.Timedelta(days=1)

        features_input = {
            'no2_mean': latest['no2_mean'], 'co_gee': latest['co_gee'], 'so2_gee': latest['so2_gee'],
            'o3_mean': latest['o3_mean'], 'nhiet_do_mean': latest['nhiet_do_mean'],
            'do_am_mean': latest['do_am_mean'], 'gio_toc_do_mean': latest['gio_toc_do_mean'],
            'mua_tong': latest['mua_tong'], 'thang': next_date.month,
            'ngay_trong_tuan': next_date.dayofweek, 'la_cuoi_tuan': int(next_date.dayofweek >= 5),
            'pm25_lag1': df['pm25_mean'].iloc[-1], 'pm25_lag2': df['pm25_mean'].iloc[-2],
            'pm25_lag3': df['pm25_mean'].iloc[-3], 'pm25_lag5': df['pm25_mean'].iloc[-5],
            'pm25_lag7': df['pm25_mean'].iloc[-7],
            'no2_lag1': df['no2_mean'].iloc[-1], 'no2_lag2': df['no2_mean'].iloc[-2],
            'gio_lag1': df['gio_toc_do_mean'].iloc[-1], 'gio_lag2': df['gio_toc_do_mean'].iloc[-2],
            'pm25_rolling3': df['pm25_mean'].iloc[-3:].mean(),
            'pm25_rolling7': df['pm25_mean'].iloc[-7:].mean(),
            'pm25_std7': df['pm25_mean'].iloc[-7:].std(),
            'pm25_delta': df['pm25_mean'].iloc[-1] - df['pm25_mean'].iloc[-2],
            'gio_rolling3': df['gio_toc_do_mean'].iloc[-3:].mean(),
            'nhietdo_x_doam': latest['nhiet_do_mean'] * latest['do_am_mean'],
        }

        X_pred = pd.DataFrame([features_input])[metadata['features']]
        pm25_pred = model.predict(X_pred)[0]

        muc_do = "Tốt" if pm25_pred <= 25 else "Trung bình" if pm25_pred <= 50 else "Kém" if pm25_pred <= 100 else "Xấu"

        ket_qua.append({
            "ngay": str(next_date.date()),
            "pm25": round(float(pm25_pred), 2),
            "muc_do": muc_do
        })

        # Thêm dòng dự báo vừa tính vào df để dùng làm lag cho ngày tiếp theo
        new_row = latest.copy()
        new_row['ngay_do'] = next_date
        new_row['pm25_mean'] = pm25_pred
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

    return ket_qua