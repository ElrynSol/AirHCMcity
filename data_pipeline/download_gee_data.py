"""
Tool tải dữ liệu GEE (Sentinel-5P) - tính riêng cho từng trạm quan trắc.
Đọc danh sách trạm từ CSDL (stations_config.py) - không hardcode.
"""

import sys
import io
import os

import ee
import pandas as pd
import argparse
from pathlib import Path
from stations_config import get_active_stations, get_engine
from sqlalchemy import text

_GOC = Path(__file__).resolve().parent.parent
SERVICE_ACCOUNT = os.getenv('GEE_SERVICE_ACCOUNT') or 'gee-data-fetcher@gee-air-quality-service.iam.gserviceaccount.com'
# Đường dẫn khóa: biến GEE_KEY_FILE (tuyệt đối, hoặc tương đối so với thư mục dự án); mặc định gee-key.json ở thư mục gốc
_k = Path(os.getenv('GEE_KEY_FILE') or 'gee-key.json')
KEY_FILE = str(_k if _k.is_absolute() else _GOC / _k)
BUFFER_METERS = 2000  # Bán kính vùng đệm quanh mỗi trạm để tính trung bình


def init_ee():
    credentials = ee.ServiceAccountCredentials(SERVICE_ACCOUNT, KEY_FILE)
    ee.Initialize(credentials)
    print("✅ Đã kết nối Earth Engine thành công.")


def download_for_station(station, start_date, end_date, scale=1113.2):
    """Tải dữ liệu GEE cho 1 trạm cụ thể (dùng buffer tròn quanh tọa độ trạm)."""
    point = ee.Geometry.Point([station['lon'], station['lat']])
    buffer_zone = point.buffer(BUFFER_METERS)

    no2_col = ee.ImageCollection('COPERNICUS/S5P/OFFL/L3_NO2') \
        .select('NO2_column_number_density').filterBounds(buffer_zone).filterDate(start_date, end_date)
    co_col = ee.ImageCollection('COPERNICUS/S5P/OFFL/L3_CO') \
        .select('CO_column_number_density').filterBounds(buffer_zone).filterDate(start_date, end_date)
    so2_col = ee.ImageCollection('COPERNICUS/S5P/OFFL/L3_SO2') \
        .select('SO2_column_number_density').filterBounds(buffer_zone).filterDate(start_date, end_date)

    def extract(image):
        date = image.date().format('YYYY-MM-dd')
        d_start = ee.Date(date)
        d_end = d_start.advance(1, 'day')

        no2_val = image.reduceRegion(ee.Reducer.mean(), buffer_zone, scale, maxPixels=1e13).get('NO2_column_number_density')
        co_val = co_col.filterDate(d_start, d_end).mean().reduceRegion(ee.Reducer.mean(), buffer_zone, scale, maxPixels=1e13).get('CO_column_number_density')
        so2_val = so2_col.filterDate(d_start, d_end).mean().reduceRegion(ee.Reducer.mean(), buffer_zone, scale, maxPixels=1e13).get('SO2_column_number_density')

        return ee.Feature(None, {'Date': date, 'NO2_Mean': no2_val, 'CO_Mean': co_val, 'SO2_Mean': so2_val})

    time_series = no2_col.map(extract)
    features = time_series.getInfo()['features']
    rows = [f['properties'] for f in features]

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.dropna(subset=['NO2_Mean', 'CO_Mean', 'SO2_Mean'])
    return df


def load_station_data_to_db(df, tram_id):
    if len(df) == 0:
        return 0
    engine = get_engine()
    inserted = 0
    with engine.begin() as conn:
        for _, row in df.iterrows():
            conn.execute(text("""
                INSERT INTO du_lieu_gee_tphcm (ngay_do, tram_id, no2_mean, co_mean, so2_mean)
                VALUES (:ngay_do, :tram_id, :no2, :co, :so2)
                ON CONFLICT (ngay_do, tram_id) DO UPDATE
                SET no2_mean = EXCLUDED.no2_mean, co_mean = EXCLUDED.co_mean,
                    so2_mean = EXCLUDED.so2_mean, ngay_cap_nhat = CURRENT_TIMESTAMP
            """), {
                'ngay_do': row['Date'], 'tram_id': tram_id,
                'no2': row['NO2_Mean'], 'co': row['CO_Mean'], 'so2': row['SO2_Mean']
            })
            inserted += 1
    return inserted


def run(start_date, end_date):
    # Đảm bảo end_date luôn sau start_date ít nhất 1 ngày để GEE filterDate hoạt động đúng
    end_date_adjusted = (pd.Timestamp(end_date) + pd.Timedelta(days=1)).strftime('%Y-%m-%d')

    init_ee()
    stations = get_active_stations()
    print(f"Sẽ tải dữ liệu cho {len(stations)} trạm, từ {start_date} đến {end_date}\n")

    for station in stations:
        print(f"--- Đang xử lý trạm {station['ma_tram']} - {station['ten_tram']} ---")
        df = download_for_station(station, start_date, end_date_adjusted)
        n = load_station_data_to_db(df, station['id'])
        print(f"    -> Đã lưu {n} ngày dữ liệu.\n")

    print("🎉 HOÀN TẤT tải dữ liệu GEE cho tất cả trạm!")

if __name__ == "__main__":
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=str, required=True)
    parser.add_argument('--end', type=str, required=True)
    args = parser.parse_args()
    run(args.start, args.end)
