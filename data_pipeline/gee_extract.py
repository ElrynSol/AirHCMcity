"""Trích xuất trực tiếp các chỉ số Sentinel-5P từ Google Earth Engine.

Ví dụ:
  python gee_extract.py --lat 10.7769 --lon 106.7009 --buffer-km 2 \
      --start 2026-09-01 --end 2026-09-30 --output gee_tphcm.csv

  python gee_extract.py --geojson phuong.geojson --start 2026-09-01 \
      --end 2026-09-30 --output gee_phuong.csv

Ngày kết thúc được tính bao gồm. GeoJSON có thể là Geometry, Feature hoặc
FeatureCollection. Mỗi feature trong FeatureCollection được xử lý riêng.
"""

import argparse
import csv
import json
import os
from datetime import date, timedelta
from pathlib import Path

import ee


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_KEY = ROOT / "gee-key.json"
DATASETS = {
    "no2_mean": ("COPERNICUS/S5P/OFFL/L3_NO2", "NO2_column_number_density"),
    "co_mean": ("COPERNICUS/S5P/OFFL/L3_CO", "CO_column_number_density"),
    "so2_mean": ("COPERNICUS/S5P/OFFL/L3_SO2", "SO2_column_number_density"),
}
CSV_FIELDS = ["ngay_do", "ma_khu_vuc", "ten_khu_vuc", "no2_mean", "co_mean", "so2_mean"]


def parse_args():
    parser = argparse.ArgumentParser(description="Lấy trực tiếp dữ liệu Sentinel-5P từ Google Earth Engine")
    area = parser.add_mutually_exclusive_group(required=True)
    area.add_argument("--geojson", help="Tệp GeoJSON ranh giới; hỗ trợ Geometry, Feature, FeatureCollection")
    area.add_argument("--lat", type=float, help="Vĩ độ điểm cần lấy dữ liệu (phải dùng cùng --lon)")
    parser.add_argument("--lon", type=float, help="Kinh độ điểm cần lấy dữ liệu")
    parser.add_argument("--buffer-km", type=float, default=2.0, help="Bán kính vùng đệm khi dùng tọa độ (mặc định 2 km)")
    parser.add_argument("--start", required=True, help="Ngày bắt đầu YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="Ngày kết thúc YYYY-MM-DD, tính bao gồm")
    parser.add_argument("--scale", type=float, default=1113.2, help="Độ phân giải lấy mẫu theo mét")
    parser.add_argument("--key-file", default=str(DEFAULT_KEY), help="Service-account JSON (mặc định gee-key.json trong thư mục dự án)")
    parser.add_argument("--project", default=os.getenv("GOOGLE_CLOUD_PROJECT"), help="Google Cloud project đã bật Earth Engine API")
    parser.add_argument("--output", default="gee_air_quality.csv", help="Đường dẫn CSV xuất ra")
    args = parser.parse_args()

    if args.lat is not None and args.lon is None:
        parser.error("Dùng --lat thì phải cung cấp --lon")
    if args.lon is not None and args.lat is None:
        parser.error("Dùng --lon thì phải cung cấp --lat")
    if args.buffer_km <= 0 or args.scale <= 0:
        parser.error("--buffer-km và --scale phải lớn hơn 0")
    try:
        args.start_date = date.fromisoformat(args.start)
        args.end_date = date.fromisoformat(args.end)
    except ValueError:
        parser.error("Ngày phải đúng định dạng YYYY-MM-DD")
    if args.end_date < args.start_date:
        parser.error("--end phải bằng hoặc sau --start")
    if (args.end_date - args.start_date).days > 366:
        parser.error("Mỗi lần lấy tối đa 367 ngày")
    return args


def read_areas(args):
    if args.geojson:
        source = Path(args.geojson)
        with source.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if data.get("type") == "FeatureCollection":
            features = data.get("features", [])
        elif data.get("type") == "Feature":
            features = [data]
        else:
            features = [{"type": "Feature", "properties": {}, "geometry": data}]
        areas = []
        for index, feature in enumerate(features, start=1):
            props = feature.get("properties") or {}
            geometry = feature.get("geometry")
            if not geometry:
                continue
            areas.append({
                "code": str(props.get("code") or feature.get("id") or index),
                "name": str(props.get("fullName") or props.get("name") or props.get("ten") or f"Khu vực {index}"),
                "geometry": geometry,
            })
        if not areas:
            raise ValueError("GeoJSON không có geometry hợp lệ")
        return areas

    if not -90 <= args.lat <= 90 or not -180 <= args.lon <= 180:
        raise ValueError("Tọa độ không hợp lệ")
    point = ee.Geometry.Point([args.lon, args.lat])
    return [{
        "code": "point",
        "name": f"{args.lat:.5f}_{args.lon:.5f}",
        "geometry": point.buffer(args.buffer_km * 1000).getInfo(),
    }]


def gee_daily_rows(geometry, start_date, end_date, scale):
    region = ee.Geometry(geometry)
    number_of_days = (end_date - start_date).days + 1
    day_offsets = ee.List.sequence(0, number_of_days - 1)

    def calculate_day(offset):
        day = ee.Date(start_date.isoformat()).advance(ee.Number(offset), "day")
        next_day = day.advance(1, "day")
        daily_bands = []

        for output_name, (collection_id, source_band) in DATASETS.items():
            collection = (ee.ImageCollection(collection_id)
                .filterBounds(region)
                .filterDate(day, next_day)
                .select(source_band))
            empty_band = ee.Image.constant(0).updateMask(ee.Image.constant(0)).rename(source_band)
            daily_image = collection.merge(ee.ImageCollection([empty_band])).mean().rename(output_name)
            daily_bands.append(daily_image)

        image = ee.Image.cat(daily_bands)
        means = image.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=region,
            scale=scale,
            maxPixels=1e13,
            bestEffort=True,
        )
        return ee.Feature(None, means.set("ngay_do", day.format("YYYY-MM-dd")))

    collection = ee.FeatureCollection(day_offsets.map(calculate_day))
    response = collection.getInfo()
    rows = []
    for feature in response.get("features", []):
        properties = feature.get("properties", {})
        rows.append({
            "ngay_do": properties.get("ngay_do"),
            **{name: properties.get(name) for name in DATASETS},
        })
    return rows


def main():
    args = parse_args()
    key_path = Path(args.key_file).expanduser().resolve()
    if not key_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy service-account JSON: {key_path}")
    with key_path.open("r", encoding="utf-8") as file:
        service_account = json.load(file).get("client_email")
    if not service_account:
        raise ValueError("Tệp credentials thiếu client_email")

    credentials = ee.ServiceAccountCredentials(service_account, str(key_path))
    if args.project:
        ee.Initialize(credentials, project=args.project)
    else:
        ee.Initialize(credentials)

    areas = read_areas(args)
    output = Path(args.output).expanduser()
    if not output.is_absolute():
        output = Path.cwd() / output
    output.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with output.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for index, area in enumerate(areas, start=1):
            print(f"[{index}/{len(areas)}] Đang lấy GEE: {area['name']}")
            values = gee_daily_rows(area["geometry"], args.start_date, args.end_date, args.scale)
            for row in values:
                writer.writerow({
                    "ngay_do": row.get("ngay_do"),
                    "ma_khu_vuc": area["code"],
                    "ten_khu_vuc": area["name"],
                    "no2_mean": row.get("no2_mean"),
                    "co_mean": row.get("co_mean"),
                    "so2_mean": row.get("so2_mean"),
                })
                count += 1
    print(f"Hoàn tất: {count} dòng dữ liệu từ GEE → {output}")


if __name__ == "__main__":
    main()
