# Cơ sở dữ liệu: vì sao chọn PostgreSQL + PostGIS

## Kết luận

AirHCM dùng **PostgreSQL 17 + PostGIS 3**. Đề tài là hệ thống thông tin môi trường gắn với **vị trí**: trạm quan trắc,
168 phường/xã, phản ánh của người dân. Các câu hỏi chính đều là câu hỏi không gian: điểm này thuộc phường nào,
trạm nào gần nhất, cách bao xa, vùng nào ô nhiễm. PostGIS trả lời các câu hỏi này **ngay trong CSDL, có chỉ mục không gian**.
SQL thường (PostgreSQL không PostGIS, MySQL, SQL Server…) chỉ lưu được vĩ độ/kinh độ dạng số và phải tự viết lại các phép toán hình học.

## So sánh

| Tiêu chí | SQL thường (vĩ độ, kinh độ là 2 cột số) | PostgreSQL + PostGIS |
|---|---|---|
| Lưu ranh giới phường (đa giác) | Không có kiểu dữ liệu; phải lưu chuỗi JSON, không truy vấn được | Kiểu `geometry(MultiPolygon, 4326)`, kiểm tra hợp lệ (`ST_IsValid`, `ST_MakeValid`) |
| Điểm thuộc phường nào | Tải 168 đa giác về ứng dụng rồi tự lập trình thuật toán điểm-trong-đa-giác | `ST_Contains(geom, điểm)` dùng chỉ mục GiST |
| Trạm gần nhất | Tính khoảng cách tới mọi trạm rồi sắp xếp (quét toàn bảng) | Toán tử KNN `ORDER BY toado <-> điểm LIMIT 1` dùng chỉ mục |
| Khoảng cách thật | Tự viết công thức Haversine, dễ sai | `ST_Distance(a::geography, b::geography)`: mét, trên mặt cầu WGS84 |
| Diện tích, đường bao thành phố | Không làm được | `ST_Area(geography)`, `ST_Union`, `ST_SimplifyPreserveTopology` |
| Xuất bản đồ web | Tự chuyển định dạng | `ST_AsGeoJSON`, Leaflet đọc trực tiếp |
| Hệ tọa độ | Không quản lý | SRID 4326 (WGS84), chuyển hệ bằng `ST_Transform` khi cần |
| Cài đặt | Đơn giản hơn | Thêm gói PostGIS (Docker image `Dockerfile.db` của dự án đã có sẵn, chạy được cả amd64 và ARM64) |
| Chuẩn | Không có | OGC Simple Features, ISO 19125 — dùng chung với QGIS, ArcGIS |

Cái giá phải trả là cài đặt nặng hơn một chút: cần gói PostGIS, và image `postgis/postgis` chính thức không có bản ARM64.
Dự án đã xử lý bằng `dong_goi/Dockerfile.db` (dựng từ `postgres:17` + gói Debian `postgresql-17-postgis-3`).

## PostGIS được dùng ở đâu trong AirHCM

| Chức năng | Bảng | Truy vấn không gian | Tệp |
|---|---|---|---|
| Ranh giới 168 phường/xã sau sáp nhập 2025 | `phuong_xa` (MultiPolygon, GiST) | `ST_GeomFromGeoJSON`, `ST_MakeValid`, `ST_Multi` khi nạp | `data_pipeline/nap_ranh_gioi.py` |
| Trạm quan trắc | `tram_quan_trac.toado` (Point, GiST) | `ST_X`, `ST_Y`, GeoAlchemy2 | `backend/models.py`, `routers/tram.py` |
| Bản đồ nhiệt: giá trị từng phường | `phuong_xa` | `ST_PointOnSurface` (điểm luôn nằm trong phường) | `services/ranh_gioi.py` |
| Độ tin cậy theo khoảng cách tới trạm | `phuong_xa` × `tram_quan_trac` | KNN `<->` + `ST_Distance(geography)` | `services/ranh_gioi.py` |
| Cắt bản đồ nhiệt theo thành phố | `phuong_xa` | `ST_Union`, `ST_SimplifyPreserveTopology`, `ST_Extent`, `ST_AsGeoJSON` | `services/ranh_gioi.py` |
| Phản ánh của người dân thuộc phường nào | `phan_anh` × `phuong_xa` | `ST_Contains(geom, ST_MakePoint(...))` | `services/phan_anh.py` |
| Quét vùng tròn (bán kính theo mét) | điểm ước tính, phản ánh | `ST_DWithin(geography)` | `services/khong_gian.py` |
| Quét khung / đa giác vẽ tay | điểm ước tính, phản ánh, phường | `ST_Intersects`, `ST_Area(ST_Intersection)` | `services/khong_gian.py` |
| Phát hiện xung đột hình học (đa giác tự cắt) | — | `ST_IsValid`, `ST_IsValidReason`, `ST_IsValidDetail` (vị trí điểm cắt), sửa bằng `ST_MakeValid` | `services/khong_gian.py` |
| Khoảng cách từ cột mốc kéo được (vị trí người dùng) | mọi điểm | `ST_Distance(geography)` | `services/khong_gian.py` |
| Tra cứu tọa độ → phường | `phuong_xa` | `ST_Contains` | `GET /api/v1/ranh-gioi/tra-cuu?lat=&lon=` |

Kiểm chứng khi nạp dữ liệu (17/11/2026): 168/168 phường hợp lệ; diện tích tính bằng `ST_Area` khớp số liệu chính thức
(TP.HCM cũ ≈ 2.030 km², Bình Dương cũ ≈ 2.697 km², Bà Rịa – Vũng Tàu cũ ≈ 1.965 km²); 16/16 trạm nằm trong đúng một phường.

## Phần vẫn làm ngoài CSDL (và lý do)

- **Nội suy IDW cho bản đồ nhiệt** chạy bằng NumPy: phải tính lại cho từng ngày dự báo trên lưới 40×40,
  vectơ hóa trong NumPy nhanh hơn và dễ kiểm thử hơn viết bằng SQL.
- **Mô hình học máy** (Random Forest, Gradient Boosting) đọc dữ liệu bảng từ CSDL rồi huấn luyện bằng scikit-learn.
