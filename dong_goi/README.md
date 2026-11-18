# Thư mục `dong_goi/` — đóng gói bản nộp và triển khai lên máy chủ

Chạy trên máy tính cá nhân thì **không cần** thư mục này (dùng `chay_server.bat` ở thư mục gốc).

| Tệp | Dùng để | Cách dùng |
|---|---|---|
| `tao_ban_nop.py` | Tạo **file zip nộp bài**: chỉ mã nguồn, dữ liệu, mô hình, APK; tự loại khóa bí mật; kèm `MUC_LUC.txt` | `python dong_goi/tao_ban_nop.py` (thêm `--kiem-thu` để chạy kiểm thử trước) |
| `kiem_tra_moi_truong.py` | Kiểm tra máy đã đủ Python, PostgreSQL/PostGIS, thư viện chưa | `python dong_goi/kiem_tra_moi_truong.py` |
| `Dockerfile` | Công thức đóng gói **máy chủ web** thành container Docker | dùng qua docker compose |
| `Dockerfile.db` | Container **CSDL PostgreSQL + PostGIS** (chạy được cả máy ARM như Oracle Cloud) | dùng qua docker compose |
| `docker-compose.yml` | Chạy thử cả hệ thống bằng Docker trên máy cá nhân | `docker compose -f dong_goi/docker-compose.yml up -d` |
| `docker-compose.prod.yml` | Chạy **trên máy chủ Internet 24/7**: CSDL + web + HTTPS (Caddy) + sao lưu hằng ngày | do `trien_khai/cai_dat_may_chu.sh` gọi |
| `Caddyfile` | Cấu hình Caddy: tự xin chứng chỉ HTTPS cho tên miền | do docker compose dùng |
| `trien_khai/cai_dat_may_chu.sh` | **Cài lần đầu** lên máy chủ Linux (Oracle/Google Cloud): cài Docker, tạo `.env`, mở cổng, khởi động | `bash dong_goi/trien_khai/cai_dat_may_chu.sh` |
| `trien_khai/cap_nhat.sh` | **Cập nhật** máy chủ khi có mã mới (tự sao lưu CSDL trước) | `bash dong_goi/trien_khai/cap_nhat.sh` |
| `trien_khai/khoi_phuc.sh` | **Khôi phục** dữ liệu từ bản sao lưu | `bash dong_goi/trien_khai/khoi_phuc.sh <tệp sao lưu>` |

Hướng dẫn từng bước: `docs/TRIEN_KHAI_ORACLE.md` (máy chủ đám mây) và `docs/HUONG_DAN_TRIEN_KHAI.md` (tên miền + Cloudflare Tunnel).
