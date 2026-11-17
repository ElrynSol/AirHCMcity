@echo off
chcp 65001 >nul
REM Đồng bộ dữ liệu (Open-Meteo + vệ tinh), tự lấy bù ngày thiếu. Chạy nền bằng pythonw: không giữ cửa sổ mở.
REM Được tác vụ cũ "Dong bo du lieu chat luong khong khi" (15:59 hằng ngày) gọi; bấm đúp để chạy tay cũng được.
REM Lịch chính: tác vụ AQI_DongBoHangNgay (cai_dat_dong_bo_tu_dong.ps1). Khóa tệp đảm bảo không chạy chồng.
cd /d "%~dp0"
start "" "%~dp0venv\Scripts\pythonw.exe" "%~dp0data_pipeline\dong_bo_hang_ngay.py" --nguon lich_windows
echo Da bat dau dong bo nen. Xem tien do o trang Trang thai du lieu hoac file log_dong_bo.txt
