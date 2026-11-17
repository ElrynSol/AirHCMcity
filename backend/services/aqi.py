"""Tiện ích tính AQI (VN_AQI theo QĐ 1459/QĐ-TCMT) dùng chung cho các router.

core/config.py đã thêm thư mục ml/ vào sys.path, nên tinh_aqi import được trực tiếp
(không cần sys.path.append thủ công ở từng nơi)."""

from core import config  # noqa: F401  (nạp .env + đường dẫn dự án, gồm ml/, trước)

from tinh_aqi import tinh_aqi_tong_hop, phan_loai_aqi  # noqa: E402


def _aqi_helpers():
    """Giữ lại cho các router đang gọi _aqi_helpers(); trả về (tinh_aqi_tong_hop, phan_loai_aqi)."""
    return tinh_aqi_tong_hop, phan_loai_aqi
