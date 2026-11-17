# Bộ dữ liệu mở AirHCM

Số liệu chất lượng không khí TP.HCM dùng để huấn luyện và đánh giá mô hình của AirHCM. Không chứa dữ liệu cá nhân.

| Tệp | Nội dung | Nguồn gốc |
|---|---|---|
| `mo/tram_quan_trac.csv` | 16 điểm quan trắc (mã, tên phường, vĩ độ, kinh độ, nhóm ô nhiễm) | AirHCM |
| `mo/du_lieu_ngay_theo_tram.csv` | Trung bình ngày theo điểm: PM2.5, PM10, CO, NO₂, SO₂, O₃ (µg/m³), nhiệt độ, độ ẩm, gió, mưa | Mô hình CAMS (Copernicus) và ERA5 qua Open-Meteo |
| `mo/ve_tinh_sentinel5p.csv` | Cột NO₂, CO, SO₂ theo ngày | Vệ tinh Sentinel-5P TROPOMI qua Google Earth Engine |
| `gio_cache.csv` | Số liệu theo giờ tại trung tâm TP.HCM từ 08/2022 | CAMS / Open-Meteo |
| `ranh_gioi/phuong_xa_hcm.geojson` | Ranh giới 168 phường/xã TP.HCM sau sáp nhập 2025 | Kho mở thanglequoc/vietnamese-provinces-database (theo Cục Đo đạc, Bản đồ và Thông tin địa lý VN) |

**Lưu ý:** CAMS là số liệu **mô hình** (độ phân giải ~40 km), không phải số đo của trạm mặt đất.
Công cụ `data_pipeline/tai_tram_that.py` đối chiếu CAMS với số đo thật (OpenAQ).

Nạp vào CSDL mới (sau khi chạy máy chủ một lần để tạo bảng): `python data_pipeline/du_lieu_mo.py --nhap`.
Xuất lại từ CSDL: `python data_pipeline/du_lieu_mo.py --xuat`.

## Giấy phép và ghi nguồn

Mã nguồn theo giấy phép MIT (tệp `LICENSE`). Dữ liệu tuân theo giấy phép của nguồn gốc:

- CAMS: "Generated using Copernicus Atmosphere Monitoring Service information" (giấy phép Copernicus, cho phép dùng lại có ghi nguồn).
- Open-Meteo: CC BY 4.0.
- Sentinel-5P: dữ liệu Copernicus Sentinel, miễn phí và mở.
- Ranh giới phường/xã: ghi nguồn kho thanglequoc/vietnamese-provinces-database khi dùng lại.
- Nền bản đồ trên web: © OpenStreetMap contributors (ODbL).
