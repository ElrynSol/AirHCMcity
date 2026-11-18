"""Ngưỡng tham chiếu chất lượng không khí dùng chung cho toàn hệ thống (một chỗ duy nhất, không viết cứng ở nơi khác).

QCVN 05:2023/BTNMT (quy chuẩn kỹ thuật quốc gia về chất lượng không khí xung quanh), đơn vị µg/Nm³:
- PM2.5 trung bình 24 giờ: 50 đến hết 31/12/2025, **45 từ 01/01/2026** (lộ trình siết dần của quy chuẩn).
- PM10 24 giờ 100; NO₂ 1 giờ 200, 24 giờ 100; SO₂ 1 giờ 350, 24 giờ 125; O₃ 1 giờ 200, 8 giờ 120; CO 1 giờ 30.000, 8 giờ 10.000.
WHO 2021 (Global Air Quality Guidelines, khuyến nghị sức khỏe, không phải quy chuẩn): PM2.5 24 giờ 15; PM10 24 giờ 45; NO₂ 24 giờ 25.

Lưu ý đơn vị: QCVN dùng µg/Nm³ (điều kiện chuẩn), số liệu mô hình CAMS dùng µg/m³ ở điều kiện thực. Ở TP.HCM (≈ 1 atm, 27–33 °C)
hai đơn vị chênh khoảng 8–10%; hệ thống so sánh trực tiếp và ghi rõ giới hạn này. "PM2.5 vượt ngưỡng QCVN" KHÁC "AQI vượt ngưỡng":
AQI tính theo QĐ 1459/QĐ-TCMT (services/aqi.py).
"""

from datetime import date, datetime

WHO_2021 = {"pm25_24h": 15.0, "pm25_nam": 5.0, "pm10_24h": 45.0, "pm10_nam": 15.0, "no2_24h": 25.0, "no2_nam": 10.0}

QCVN_05_2023 = {
    "pm10_24h": 100.0, "pm10_nam": 50.0,
    "no2_1h": 200.0, "no2_24h": 100.0,
    "so2_1h": 350.0, "so2_24h": 125.0,
    "o3_1h": 200.0, "o3_8h": 120.0,
    "co_1h": 30000.0, "co_8h": 10000.0,
}
_NGAY_SIET_PM25 = date(2026, 1, 1)


def qcvn_pm25_24h(ngay=None) -> float:
    """Ngưỡng PM2.5 trung bình 24 giờ QCVN 05:2023 áp dụng cho ngày `ngay` (mặc định hôm nay)."""
    if ngay is None:
        ngay = date.today()
    elif isinstance(ngay, datetime):
        ngay = ngay.date()
    elif isinstance(ngay, str):
        ngay = date.fromisoformat(ngay[:10])
    return 45.0 if ngay >= _NGAY_SIET_PM25 else 50.0


def bang_nguong(ngay=None) -> dict:
    """Toàn bộ ngưỡng tại một ngày, dùng cho API /api/v1/nguong và giao diện."""
    return {"ngay_ap_dung": str(ngay or date.today()),
            "qcvn_05_2023": {"pm25_24h": qcvn_pm25_24h(ngay), **QCVN_05_2023, "don_vi": "µg/Nm³"},
            "who_2021": {**WHO_2021, "don_vi": "µg/m³"},
            "ghi_chu": "PM2.5 24 giờ theo QCVN 05:2023: 50 µg/Nm³ đến 31/12/2025, 45 µg/Nm³ từ 01/01/2026. "
                       "Số liệu CAMS ở điều kiện thực (µg/m³), chênh khoảng 8–10% so với điều kiện chuẩn."}
