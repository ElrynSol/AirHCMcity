"""
Pipeline tổng: Tải dữ liệu GEE -> Làm sạch -> Nạp vào PostgreSQL
Chạy 1 lệnh duy nhất, tham số hóa khung thời gian.
"""

import argparse
from download_gee_data import download_air_quality_data
from load_to_db import load_csv_to_db


def run_full_pipeline(start_date, end_date, khu_vuc="TP.HCM"):
    print("=" * 60)
    print(f"BẮT ĐẦU PIPELINE: {start_date} -> {end_date}")
    print("=" * 60)

    csv_file = f"data_gee_{start_date}_{end_date}.csv"

    # Bước 1: Tải và làm sạch dữ liệu từ GEE
    print("\n### BƯỚC 1: TẢI DỮ LIỆU TỪ GEE ###")
    df = download_air_quality_data(start_date, end_date, csv_file)

    if len(df) == 0:
        print("⚠️ Không có dữ liệu sạch nào để nạp vào DB. Dừng pipeline.")
        return

    # Bước 2: Nạp vào PostgreSQL
    print("\n### BƯỚC 2: NẠP VÀO POSTGRESQL ###")
    load_csv_to_db(csv_file, khu_vuc)

    print("\n" + "=" * 60)
    print("✅ PIPELINE HOÀN TẤT TOÀN BỘ!")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline tự động: GEE -> CSV -> PostgreSQL")
    parser.add_argument('--start', type=str, required=True, help='Ngày bắt đầu YYYY-MM-DD')
    parser.add_argument('--end', type=str, required=True, help='Ngày kết thúc YYYY-MM-DD')
    parser.add_argument('--khu-vuc', type=str, default='TP.HCM')

    args = parser.parse_args()
    run_full_pipeline(args.start, args.end, args.khu_vuc)