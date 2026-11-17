"""
Chạy pipeline tự động theo từng tháng, cho một khoảng năm.
Tránh lỗi "Collection query aborted after accumulating over 5000 elements"
khi tải nguyên 1 năm cùng lúc.
"""

import argparse
from datetime import date
from dateutil.relativedelta import relativedelta
from run_pipeline import run_full_pipeline


def run_batch(start_year, end_year, end_month_limit=None):
    current = date(start_year, 1, 1)
    final = date(end_year, 12, 31)
    if end_month_limit:
        final = end_month_limit

    while current <= final:
        month_end = (current + relativedelta(months=1)) - relativedelta(days=1)
        if month_end > final:
            month_end = final

        start_str = current.strftime('%Y-%m-%d')
        end_str = month_end.strftime('%Y-%m-%d')

        print(f"\n\n>>>>>> ĐANG XỬ LÝ THÁNG: {start_str} -> {end_str} <<<<<<")
        try:
            run_full_pipeline(start_str, end_str)
        except Exception as e:
            print(f"❌ LỖI ở tháng {start_str} - {end_str}: {e}")
            print("Bỏ qua, tiếp tục tháng kế tiếp...")

        current = current + relativedelta(months=1)

    print("\n\n" + "=" * 60)
    print("🎉 ĐÃ CHẠY XONG TOÀN BỘ CÁC THÁNG TRONG KHOẢNG YÊU CẦU!")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--start-year', type=int, required=True)
    parser.add_argument('--end-year', type=int, required=True)
    parser.add_argument('--end-date', type=str, default=None,
                         help='Giới hạn ngày cuối cùng, VD 2026-09-24 (tùy chọn)')

    args = parser.parse_args()

    end_limit = None
    if args.end_date:
        y, m, d = map(int, args.end_date.split('-'))
        end_limit = date(y, m, d)

    run_batch(args.start_year, args.end_year, end_limit)