# Thư mục `models/` — mô hình đã huấn luyện và kết quả đánh giá

Không cần mở hay sửa tay các tệp ở đây. Máy chủ tự đọc khi chạy; muốn tạo lại thì chạy lệnh ở cột cuối (từ thư mục gốc dự án).

| Tệp | Là gì | Ai dùng | Tạo lại bằng |
|---|---|---|---|
| `random_forest_pm25_du_bao.pkl` | Mô hình **dự báo PM2.5 ngày mai và 7 ngày** (Random Forest) | trang Dự báo | `python ml/train_model.py` |
| `random_forest_pm25.pkl`, `linear_pm25.pkl` | Mô hình **ước lượng PM2.5 trong ngày** từ thời tiết và khí vệ tinh | trang Kịch bản | `python ml/train_model.py` |
| `model_metadata.pkl` / `.json` | Thông tin kèm mô hình: tên đặc trưng, sai số, kỹ năng, khoảng dữ liệu huấn luyện (`.json` là bản đọc được của `.pkl`) | Dự báo, Kịch bản, Thống kê | `python ml/train_model.py` |
| `du_bao_gio.joblib` | Mô hình **dự báo theo giờ 1–24 giờ** (HistGradientBoosting) | trang Dự báo, Tổng quan | `python ml/train_du_bao_gio.py` |
| `du_bao_gio_chi_so.json` | Sai số, kỹ năng từng tầm dự báo theo giờ | trang Dự báo, Phương pháp | `python ml/train_du_bao_gio.py` |
| `random_forest_pm25_diem.pkl` | Mô hình theo **từng điểm đo** cho bản đồ nhiệt | trang Bản đồ nhiệt | `python ml/train_diem.py` |
| `diem_chi_so.json` | Sai số mô hình theo điểm đo và nội suy không gian | trang Bản đồ nhiệt | `python ml/train_diem.py` |
| `danh_gia_xac_suat.json` | **Kiểm chứng xác suất** trên các ngày mô hình chưa học: PICP, Brier, bảng độ tin cậy | trang Dự báo (chi tiết kỹ thuật) | `python ml/danh_gia_xac_suat.py` |
| `bao_cao_chat_luong_du_lieu.json` | Báo cáo chất lượng dữ liệu: thiếu ngày, giá trị bất thường | trang Trạng thái dữ liệu | `python data_pipeline/kiem_tra_du_lieu.py` |
| `kmeans_phan_cum.pkl` | Phân cụm điểm đo theo mức ô nhiễm (nhóm "ô nhiễm cao/thấp") | gán nhóm trạm | `python ml/phan_cum_tram.py` |
| `downscale_*.pkl` | Thử nghiệm cũ: chi tiết hóa PM2.5/PM10/O₃ từ lưới thô. **Máy chủ không dùng** | — | `python ml/train_downscale_model.py` |

`.pkl` / `.joblib` là định dạng lưu mô hình của Python (pickle). Chỉ nạp tệp mô hình từ nguồn tin cậy.
