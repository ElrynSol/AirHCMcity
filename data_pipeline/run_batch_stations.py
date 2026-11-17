"""
Chạy tải dữ liệu GEE theo từng trạm, cho toàn bộ khoảng thời gian, chia theo tháng.
Có xử lý lỗi để không dừng giữa chừng nếu 1 tháng gặp sự cố.
"""

import argparse
from datetime import date
from dateutil.relativedelta import relativedelta
from download_gee_data import run as run_gee_for_month


def run_batch(start_year, end_year, end_date_limit=None):
    current = date(start_year, 1, 1)
    final = date(end_year, 12, 31)
    if end_date_limit:
        final = end_date_limit

    total_months = 0
    while current <= final:
        month_end = (current + relativedelta(months=1)) - relativedelta(days=1)
        if month_end > final:
            month_end = final

        start_str = current.strftime('%Y-%m-%d')
        end_str = month_end.strftime('%Y-%m-%d')

        print(f"\n{'='*70}")
        print(f">>> THÁNG {start_str} -> {end_str} <<<")
        print(f"{'='*70}")

        try:
            run_gee_for_month(start_str, end_str)
            total_months += 1
        except Exception as e:
            print(f"❌ LỖI ở tháng {start_str} - {end_str}: {e}")
            print("Bỏ qua, tiếp tục tháng kế tiếp...")

        current = current + relativedelta(months=1)

    print(f"\n\n{'='*70}")
    print(f"🎉 HOÀN TẤT! Đã xử lý {total_months} tháng cho tất cả các trạm.")
    print(f"{'='*70}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--start-year', type=int, required=True)
    parser.add_argument('--end-year', type=int, required=True)
    parser.add_argument('--end-date', type=str, default=None)
    args = parser.parse_args()

    end_limit = None
    if args.end_date:
        y, m, d = map(int, args.end_date.split('-'))
        end_limit = date(y, m, d)

    run_batch(args.start_year, args.end_year, end_limit)