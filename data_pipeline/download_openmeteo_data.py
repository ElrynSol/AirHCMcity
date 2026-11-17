"""
Tool tải dữ liệu Open-Meteo (khí quyển + khí tượng) - tính riêng cho từng trạm.
Đọc danh sách trạm từ CSDL (stations_config.py) - không hardcode.
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import requests
import pandas as pd
import argparse
import time
from stations_config import get_active_stations, get_engine
from sqlalchemy import text

def fetch_air_quality(lat, lon, start_date, end_date):
    url = "https://air-quality-api.open-meteo.com/v1/air-quality"
    params = {
        "latitude": lat, "longitude": lon,
        "hourly": "pm2_5,pm10,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone",
        "start_date": start_date, "end_date": end_date,
        "timezone": "Asia/Bangkok"
    }
    resp = requests.get(url, params=params, timeout=60)
    resp.raise_for_status()
    h = resp.json()['hourly']
    df = pd.DataFrame({
        'time': h['time'], 'pm2_5': h['pm2_5'], 'pm10': h['pm10'],
        'co': h['carbon_monoxide'], 'no2': h['nitrogen_dioxide'],
        'so2': h['sulphur_dioxide'], 'o3': h['ozone'],
    })
    df['time'] = pd.to_datetime(df['time'])
    return df


def fetch_weather(lat, lon, start_date, end_date):
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat, "longitude": lon,
        "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation",
        "start_date": start_date, "end_date": end_date,
        "timezone": "Asia/Bangkok"
    }
    resp = requests.get(url, params=params, timeout=60)
    resp.raise_for_status()
    h = resp.json()['hourly']
    df = pd.DataFrame({
        'time': h['time'], 'nhiet_do': h['temperature_2m'],
        'do_am': h['relative_humidity_2m'], 'gio_toc_do': h['wind_speed_10m'],
        'mua': h['precipitation'],
    })
    df['time'] = pd.to_datetime(df['time'])
    return df


def aggregate_daily(df_aq, df_weather):
    df_aq['ngay_do'] = df_aq['time'].dt.date
    df_weather['ngay_do'] = df_weather['time'].dt.date

    daily_aq = df_aq.groupby('ngay_do').agg({
        'pm2_5': 'mean', 'pm10': 'mean', 'co': 'mean',
        'no2': 'mean', 'so2': 'mean', 'o3': 'mean'
    }).reset_index()

    daily_weather = df_weather.groupby('ngay_do').agg({
        'nhiet_do': 'mean', 'do_am': 'mean',
        'gio_toc_do': 'mean', 'mua': 'sum'
    }).reset_index()

    merged = pd.merge(daily_aq, daily_weather, on='ngay_do', how='inner')
    merged = merged.dropna()
    return merged.round(4)


def load_to_db(df, tram_id):
    if len(df) == 0:
        return 0
    engine = get_engine()
    inserted = 0
    with engine.begin() as conn:
        for _, row in df.iterrows():
            conn.execute(text("""
                INSERT INTO du_lieu_tram_mat_dat
                (ngay_do, tram_id, pm25_mean, pm10_mean, co_mean, no2_mean, so2_mean, o3_mean,
                 nhiet_do_mean, do_am_mean, gio_toc_do_mean, mua_tong)
                VALUES (:ngay_do, :tram_id, :pm25, :pm10, :co, :no2, :so2, :o3,
                        :nhiet_do, :do_am, :gio, :mua)
                ON CONFLICT (ngay_do, tram_id) DO UPDATE
                SET pm25_mean = EXCLUDED.pm25_mean, pm10_mean = EXCLUDED.pm10_mean,
                    co_mean = EXCLUDED.co_mean, no2_mean = EXCLUDED.no2_mean,
                    so2_mean = EXCLUDED.so2_mean, o3_mean = EXCLUDED.o3_mean,
                    nhiet_do_mean = EXCLUDED.nhiet_do_mean, do_am_mean = EXCLUDED.do_am_mean,
                    gio_toc_do_mean = EXCLUDED.gio_toc_do_mean, mua_tong = EXCLUDED.mua_tong,
                    ngay_cap_nhat = CURRENT_TIMESTAMP
            """), {
                'ngay_do': row['ngay_do'], 'tram_id': tram_id,
                'pm25': row['pm2_5'], 'pm10': row['pm10'], 'co': row['co'],
                'no2': row['no2'], 'so2': row['so2'], 'o3': row['o3'],
                'nhiet_do': row['nhiet_do'], 'do_am': row['do_am'],
                'gio': row['gio_toc_do'], 'mua': row['mua']
            })
            inserted += 1
    return inserted


def run(start_date, end_date):
    stations = get_active_stations()
    print(f"Sẽ tải dữ liệu Open-Meteo cho {len(stations)} trạm, từ {start_date} đến {end_date}\n")

    for station in stations:
        print(f"--- Đang xử lý trạm {station['ma_tram']} - {station['ten_tram']} ---")
        try:
            df_aq = fetch_air_quality(station['lat'], station['lon'], start_date, end_date)
            time.sleep(2)  # nghỉ 2 giây giữa 2 lần gọi API để tránh bị giới hạn
            df_weather = fetch_weather(station['lat'], station['lon'], start_date, end_date)
            df_daily = aggregate_daily(df_aq, df_weather)
            n = load_to_db(df_daily, station['id'])
            print(f"    -> Đã lưu {n} ngày dữ liệu.\n")
        except Exception as e:
            print(f"    ❌ Lỗi: {e}. Bỏ qua, thử lại sau.\n")

        time.sleep(3)  # nghỉ 3 giây trước khi sang trạm tiếp theo

    print("🎉 HOÀN TẤT tải dữ liệu Open-Meteo cho tất cả trạm!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=str, required=True)
    parser.add_argument('--end', type=str, required=True)
    args = parser.parse_args()
    run(args.start, args.end)