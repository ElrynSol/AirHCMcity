# Phương pháp dự báo, độ phân giải, tích hợp dữ liệu và đánh giá mô hình

Tài liệu này tóm tắt bốn nội dung cốt lõi của AirHCM và chỉ đến đúng tệp mã nguồn thực hiện từng nội dung.
Mọi thông tin dưới đây cũng được trả về bằng API `GET /api/v1/phuong-phap` (mã ở `backend/core/phuong_phap.py`)
và hiển thị ở trang **Phương pháp** (`frontend/phuong-phap.html`, 4 mục đầu). Các con số đánh giá không ghi tay:
API đọc trực tiếp từ tệp kết quả trong `models/` do các script huấn luyện ghi ra. Kiểm thử `tests/test_phuong_phap.py`
bảo đảm danh sách đặc trưng hiển thị khớp với mô hình đang chạy.

## 1. Mô hình dự báo theo từng chỉ số và tầm dự báo

| Chỉ số | Tầm dự báo | Độ phân giải đầu ra | Mô hình vận hành | Đối chứng | Mã nguồn |
|---|---|---|---|---|---|
| PM2.5 | 1–24 giờ | Giờ · trung tâm TP | HistGradientBoosting (một mô hình cho 24 bước, học mức thay đổi so với hiện tại; 26 đặc trưng) | Persistence, cùng giờ hôm qua | `ml/train_du_bao_gio.py`, `backend/services/du_bao_gio.py` |
| PM2.5 | Ước lượng trong ngày | Ngày · trung bình TP | Random Forest (26 đặc trưng khí tượng, vệ tinh, độ trễ) | Hồi quy tuyến tính, cây quyết định | `ml/train_model.py` |
| PM2.5 → VN_AQI | Ngày mai, 7 ngày (lặp nhiều bước) | Ngày · trung bình TP | Random Forest (12 đặc trưng chuỗi PM2.5 + lịch) | Hồi quy tuyến tính, mai = hôm nay | `ml/train_model.py`, `ml/predict.py` |
| Xác suất vượt WHO 15 / QCVN 45 | Ngày mai – 7 ngày | Ngày · trung bình TP | Phân vị sai số của Random Forest | Tần suất khí hậu | `ml/danh_gia_xac_suat.py` |
| PM2.5, PM10, O3 | Ngày mai | Ngày · trung bình TP | Ridge hoặc Random Forest, tự chọn theo KTC 95% | Mai = hôm nay | `ml/du_bao_da_chat.py` |
| PM2.5 | 1–6 tháng | Tháng · trung bình TP | Khí hậu học theo tháng + dị thường 30 ngày tắt dần 0,5^k | Tháng sau = tháng trước | `ml/predict.py` (`du_bao_theo_thang_tu_chuoi`) |
| PM2.5 đo thật (CMT8) | Ngày mai | Ngày · 1 điểm đo | Ridge / Random Forest học từ số đo thật + CAMS, thời tiết ngày mai | Mai = hôm nay, CAMS thô, CAMS bù độ lệch | `ml/mo_hinh_tram_that.py` |
| PM2.5 theo khu vực | 1–7 ngày | Ngày · 168 phường/xã | Random Forest chung cho các điểm → nội suy IDW | Mai = hôm nay tại từng điểm | `ml/train_diem.py`, `backend/services/ban_do_nhiet.py` |
| Ngày vượt 25 µg/m³ | Ngày mai | Ngày | Random Forest (so với KNN, cây quyết định) — thực nghiệm | — | `ml/notebooks/02_phan_loai_canh_bao_pm25.ipynb` |

NO2, CO, SO2 **không được dự báo**: nguồn duy nhất là cột khí vệ tinh Sentinel-5P (mol/m², trễ 1–2 tuần),
không phải nồng độ sát mặt đất, nên không quy đổi VN_AQI.

## 2. Độ phân giải không gian – thời gian

| Khâu | Không gian | Thời gian |
|---|---|---|
| Dữ liệu gốc | CAMS lưới ≈ 0,4° (≈ 44 km); khí tượng ECMWF IFS ≈ 9 km / ERA5 0,25°; Sentinel-5P điểm ảnh ≈ 3,5–7 × 5,5 km (lấy mẫu lưới 1,1 km); OpenAQ 3 điểm | Giờ (CAMS, ERA5, OpenAQ); ngày (vệ tinh) |
| Lưu trong CSDL | 17 điểm ước tính (PostGIS Point) + 3 điểm đo thật | Ngày; bộ đệm giờ cho mô hình 24 h |
| Đầu vào mô hình | Trung bình thành phố, từng điểm, hoặc điểm CMT8 | Giờ, ngày, tháng |
| Hiển thị | 168 phường/xã, lưới IDW 40 × 40 | Giờ, ngày, tháng |

**Độ phân giải hiệu dụng** (`ml/danh_gia_noi_suy.py` → `models/danh_gia_noi_suy.json`): vì lưới CAMS rộng,
nhiều điểm rơi vào cùng một ô và nhận chuỗi PM2.5 giống hệt nhau. Năm 2022–2025: 13 điểm thuộc 4 ô lưới CAMS;
năm 2026: 17 điểm thuộc 8 ô (khí tượng: 10 và 14 ô). Bản đồ 168 phường/xã vì vậy là độ phân giải *hiển thị*;
độ phân giải *thông tin* là số ô lưới. Kiểm chéo bỏ một ô (đã gộp điểm cùng ô để tránh lạc quan giả tạo):
IDW RMSE 6,42 µg/m³ so với 8,55 khi lấy trung bình các ô còn lại (tốt hơn 24,9%, 97 ngày đủ ≥ 5 ô).

## 3. Tích hợp dữ liệu đa nguồn

1. **Thu thập** — `data_pipeline/dong_bo_hang_ngay.py` gọi từng nguồn cho từng điểm, tự lấy bù ngày thiếu.
2. **Đồng bộ không gian** — CAMS/ERA5: ô lưới chứa tọa độ điểm; Sentinel-5P: trung bình vòng bán kính 2 km
   (`data_pipeline/download_gee_data.py`); điểm thuộc phường nào: `ST_Contains` (`backend/services/ranh_gioi.py`).
3. **Đồng bộ thời gian** — mọi nguồn về giờ Việt Nam (GMT+7), làm tròn đầu giờ; gộp ngày = trung bình
   (mưa = tổng); ngày đo thật chỉ tính khi có ≥ 18/24 giờ (`ml/mo_hinh_tram_that.py`).
4. **Chuẩn hóa đơn vị** — nồng độ µg/m³; cột khí vệ tinh mol/m² lưu bảng riêng `du_lieu_gee_tphcm`.
5. **Kiểm soát chất lượng** — loại giá trị âm và mã lỗi thiết bị ≥ 900 µg/m³ (`data_pipeline/tai_tram_that.py`);
   kiểm tra khoảng hợp lý, ngày thiếu, giá trị đứng yên (`data_pipeline/kiem_tra_du_lieu.py`); ngày thiếu để trống.
6. **Ghép và lưu** — khóa (điểm, ngày), ràng buộc duy nhất `(tram_id, ngay_do)` + `INSERT … ON CONFLICT DO UPDATE`
   (`backend/sql/bang_du_lieu.sql`): nạp lại không sinh bản ghi trùng.
7. **Ghép cho mô hình** — nối theo ngày trên lịch liên tục để độ trễ đúng nghĩa; đặc trưng chỉ dùng thông tin
   có trước thời điểm dự báo (kiểm thử `test_dac_trung_khong_nhin_tuong_lai`).

## 4. Đánh giá mô hình

Quy trình: chia theo thời gian (không xáo trộn) → so với mốc persistence bằng kỹ năng = 1 − RMSE/RMSE_mốc →
khoảng tin cậy 95% bằng bootstrap khối 7 ngày → kiểm chéo cuốn chiếu, tách mùa khô/mưa → dự báo xác suất đánh giá
bằng PICP và Brier → đối chiếu với số đo thật OpenAQ.

Quy tắc kết luận (`ket_luan()` trong `backend/core/phuong_phap.py`, có kiểm thử):

| Kết luận | Điều kiện | Cách dùng |
|---|---|---|
| Đạt | cận dưới KTC 95% > 0 | Dùng để dự báo |
| Tham khảo | kỹ năng > 0 nhưng KTC chứa 0 | Hiển thị kèm ghi chú tham khảo |
| Chưa hơn mốc | kỹ năng ≤ 0 | Chỉ dùng cho mục đích khác (so sánh tương đối giữa khu vực) |

Chạy lại toàn bộ đánh giá:

```
venv\Scripts\python ml\train_du_bao_gio.py
venv\Scripts\python ml\train_model.py
venv\Scripts\python ml\du_bao_da_chat.py
venv\Scripts\python ml\mo_hinh_tram_that.py
venv\Scripts\python ml\train_diem.py
venv\Scripts\python ml\danh_gia_xac_suat.py
venv\Scripts\python ml\danh_gia_noi_suy.py
```
