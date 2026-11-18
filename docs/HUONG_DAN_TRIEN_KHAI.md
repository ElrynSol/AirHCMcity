# Hướng dẫn triển khai và vận hành AirHCM

Địa chỉ công khai: **https://airhcmcity.asia** (HTTPS, tên miền riêng). Máy chủ chạy trên máy tính cá nhân và đưa ra Internet
qua Cloudflare Tunnel; web truy cập được khi máy chủ đang bật.

## 1. Mô hình triển khai

```
Người dùng (trình duyệt / app Android) ──HTTPS──► Cloudflare (DNS, chứng chỉ, chống DDoS)
        ──đường hầm mã hóa──► cloudflared trên máy chủ ──► AirHCM (FastAPI, cổng 8000) ──► PostgreSQL + PostGIS
```

Đường hầm do máy chủ chủ động kết nối ra ngoài, nên không cần mở cổng router và không lộ địa chỉ IP của máy.

## 2. Các bước đã thực hiện

| # | Bước | Thao tác chính |
|---|---|---|
| 1 | Mua tên miền | Đăng ký `airhcmcity.asia` (1 năm) tại nhà đăng ký trong nước; không mua dịch vụ kèm theo, không bật DNSSEC |
| 2 | Chuyển DNS sang Cloudflare | Thêm tên miền vào Cloudflare (gói Free), đổi nameserver tại nhà đăng ký sang 2 nameserver Cloudflare |
| 3 | Tạo đường hầm | Cài `cloudflared`; `tunnel login` → `tunnel create airhcm` → khai báo `config.yml` trỏ `http://127.0.0.1:8000` → `tunnel route dns` cho tên miền chính và `www` |
| 4 | Kiểm tra ứng dụng sau proxy HTTPS | Cookie `Secure`, chống CSRF theo Origin, địa chỉ trả về OAuth lấy theo tên miền, `sitemap.xml` và thẻ `canonical` đúng tên miền |
| 5 | Đăng nhập Google | Thêm tên miền vào *Authorized JavaScript origins* và *Authorized redirect URIs* của OAuth client |
| 6 | Google Search Console | Thêm tài sản kiểu *Miền*, xác minh bằng bản ghi TXT, gửi `https://airhcmcity.asia/sitemap.xml`, yêu cầu lập chỉ mục các trang chính |
| 7 | App Android | Ghi `TEN_MIEN` vào `.env`, chạy `npm run apk`; app kết nối `https://airhcmcity.asia` qua 4G/Wi-Fi bất kỳ |

## 3. Vận hành

| Việc | Thao tác |
|---|---|
| Bật web công khai | Bấm đúp `chay_cong_khai.bat` (tự bật máy chủ nếu chưa chạy, rồi mở đường hầm) |
| Chỉ chạy trên máy | Bấm đúp `chay_server.bat`, mở http://localhost:8000 |
| Tắt web công khai | Đóng cửa sổ `chay_cong_khai.bat` |
| Kiểm tra trước khi trình diễn | `venv\Scripts\python.exe tools\kiem_thu_luong_du_lieu.py` (5/5 luồng phải đạt) |
| Tải app Android | https://airhcmcity.asia/tai-app.html |
| Theo dõi truy cập | Cloudflare → Web Analytics; Google Search Console → Hiệu suất, Trang |

## 4. Giới hạn và hướng phát triển

- Web chỉ truy cập được khi máy chủ đang bật. Muốn chạy liên tục 24/7, dùng bộ triển khai Docker có sẵn
  (`dong_goi/docker-compose.prod.yml`, `dong_goi/trien_khai/cai_dat_may_chu.sh`) trên máy chủ đám mây (Oracle Cloud Always Free,
  Google Cloud…), rồi trỏ tên miền sang máy chủ đó; người dùng vẫn dùng đúng địa chỉ cũ.
- Khóa của đường hầm nằm ở thư mục người dùng (`~/.cloudflared/`), không nằm trong mã nguồn và không đưa lên GitHub.
