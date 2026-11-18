# Triển khai AirHCM lên Internet 24/7 — Oracle Cloud Always Free

Sau khi làm theo tài liệu này, web chạy liên tục **kể cả khi máy tính cá nhân đã tắt**, có HTTPS, có tên miền.
Điện thoại (trình duyệt hoặc app) dùng được ở mọi nơi qua 4G/Wi-Fi. Máy chủ tự đồng bộ dữ liệu hằng ngày và tự gửi cảnh báo.
Google tìm thấy trang nhờ sitemap và thẻ SEO.

```
Người dùng ──HTTPS──► Caddy (chứng chỉ Let's Encrypt tự gia hạn) ──► AirHCM (FastAPI) ──► PostgreSQL + PostGIS
                            máy ảo Oracle Ampere A1 (ARM64) · Ubuntu 24.04 · Docker            └─ sao lưu tự động 02:30
```

Chi phí: **0 đồng** trong giới hạn Always Free (tối đa 4 OCPU ARM, 24 GB RAM, 200 GB ổ đĩa).

## Bước 1 — Tạo tài khoản và máy ảo (khoảng 20 phút)

1. Đăng ký tại https://www.oracle.com/cloud/free/. Cần thẻ Visa/Mastercard để xác minh; Oracle chỉ tạm giữ khoảng 1 USD rồi hoàn lại.
   **Home Region** chọn *Singapore* hoặc *Japan East (Tokyo)*: gần Việt Nam nên nhanh hơn. Không đổi được về sau.
2. Vào **Compute → Instances → Create instance**:
   - **Image**: Canonical Ubuntu 24.04
   - **Shape**: Ampere → `VM.Standard.A1.Flex`, chọn **2 OCPU, 12 GB RAM** (để dành phần miễn phí cho việc khác)
   - **SSH keys**: chọn *Generate a key pair for me*, rồi **tải khóa riêng (private key) về**. Mất khóa này là mất quyền vào máy.
   - **Boot volume**: 50 GB
   - Nếu báo *Out of capacity* (máy ARM miễn phí hay hết chỗ): thử Availability Domain khác hoặc thử lại sau vài giờ.
3. Ghi lại **Public IP address** của máy ảo.

> ⚠️ **Chính sách thu hồi máy nhàn rỗi.** Oracle có thể thu hồi máy Always Free nếu trong 7 ngày cả CPU, mạng và RAM đều dùng dưới 20%.
> AirHCM dùng khá ít tài nguyên, nên cách chắc chắn là nâng tài khoản lên **Pay As You Go** (Billing → Upgrade). Sau khi nâng,
> máy vẫn **miễn phí** trong giới hạn Always Free nhưng không bị thu hồi. Nên đặt thêm *Budget alert* 1 USD để yên tâm.

## Bước 2 — Mở cổng web (5 phút)

**Networking → Virtual Cloud Networks →** VCN của máy → **Security Lists → Default Security List → Add Ingress Rules**:

| Source CIDR | IP Protocol | Destination Port |
|---|---|---|
| `0.0.0.0/0` | TCP | `80` |
| `0.0.0.0/0` | TCP | `443` |
| `0.0.0.0/0` | UDP | `443` |

(Tường lửa bên trong Ubuntu do script ở bước 5 tự mở.)

## Bước 3 — Tên miền miễn phí (5 phút)

1. Vào https://www.duckdns.org, đăng nhập bằng Google/GitHub.
2. Tạo tên miền con, ví dụ `airhcm-1250080037` → được `airhcm-1250080037.duckdns.org`.
3. Ô **current ip**: điền Public IP của máy ảo, bấm **update ip**.

(Có tên miền riêng, ví dụ mua ở Mắt Bão hay Tenten, thì tạo bản ghi `A` trỏ về Public IP là được.)

## Bước 4 — Chép mã nguồn lên máy chủ (10 phút)

Trên **máy Windows**, trong thư mục dự án:

```powershell
venv\Scripts\python.exe dong_goi\tao_ban_nop.py --khong-apk      # tạo ..\AirHCM_1250080037_<ngày>.zip (đã loại mọi khóa bí mật)
pg_dump -U postgres -d air_quality_db --no-owner -f $env:USERPROFILE\.airhcm\backup.sql   # bản sao dữ liệu, lưu NGOÀI thư mục đồng bộ OneDrive

# chép lên máy chủ (đổi đường dẫn khóa SSH và IP)
scp -i C:\duong\dan\ssh-key.key ..\AirHCM_1250080037_*.zip $env:USERPROFILE\.airhcm\backup.sql $env:USERPROFILE\.airhcm\gee-key.json ubuntu@<PUBLIC_IP>:~
```

`backup.sql` chứa tài khoản người dùng và `gee-key.json` là khóa Google, nên chỉ chép thẳng lên máy chủ của bạn, không gửi qua kênh khác.

## Bước 5 — Cài đặt bằng 1 lệnh (10–20 phút, chủ yếu là chờ build)

```bash
ssh -i ssh-key.key ubuntu@<PUBLIC_IP>
sudo apt-get update && sudo apt-get install -y unzip
unzip AirHCM_1250080037_*.zip && cd AirHCM
mv ~/gee-key.json . 2>/dev/null || true
bash dong_goi/trien_khai/cai_dat_may_chu.sh
```

Script sẽ hỏi 3 thông tin: **tên miền** (vd. `airhcm-1250080037.duckdns.org`), **email** nhận thông báo chứng chỉ HTTPS,
và **email admin** (tài khoản đăng ký bằng email này mới có quyền quản trị). Các việc còn lại script tự làm:

- Cài Docker; thêm swap nếu RAM ít; mở cổng 80/443 trong iptables.
- Tạo `.env` với mật khẩu CSDL và khóa JWT ngẫu nhiên; đặt `MOI_TRUONG=production`, `OTP_DEMO=0`.
- Kiểm tra tên miền đã trỏ đúng IP chưa.
- Build và chạy 4 dịch vụ: CSDL, máy chủ, Caddy (HTTPS) và sao lưu hằng ngày.

## Bước 6 — Khôi phục dữ liệu và cấu hình thêm

```bash
bash dong_goi/trien_khai/khoi_phuc.sh ~/backup.sql          # nạp dữ liệu trạm, số liệu, tài khoản cũ
nano .env                                                   # điền SMTP_USER/SMTP_PASS (email OTP + cảnh báo), GEMINI_API_KEY
docker compose -f dong_goi/docker-compose.prod.yml up -d    # áp dụng .env mới
```

Không khôi phục thì CSDL trống: đăng ký tài khoản admin, thêm trạm ở trang Danh sách trạm,
rồi bấm "Đồng bộ ngay" ở trang Trạng thái dữ liệu (máy chủ tự tải bù số liệu).

## Bước 7 — Kiểm tra

Mở `https://<tên-miền>` trên điện thoại (4G, không dùng chung Wi-Fi với máy tính) để chắc chắn web truy cập được từ Internet.
Sau đó chạy kiểm thử đầu-cuối từ máy Windows:

```powershell
venv\Scripts\python.exe tools\kiem_thu_luong_du_lieu.py --may-chu https://<tên-miền>
```

Với `--may-chu https://...`, luồng 1 (nguồn ngoài) và 4 (API) kiểm chính máy chủ Internet.
Luồng 2, 3, 6 đọc CSDL theo `.env` của máy đang chạy lệnh, tức là kiểm CSDL trên máy Windows của bạn.
Tình trạng đồng bộ của máy chủ xem ở trang **Trạng thái dữ liệu** trên web.

## Bước 8 — Google tìm thấy trang (SEO)

1. Vào https://search.google.com/search-console → **Thêm tài sản** → *Tiền tố URL* → `https://<tên-miền>/`.
2. Chọn xác minh bằng **Thẻ HTML**, chép giá trị `content="..."` vào `.env`: `GOOGLE_SITE_VERIFICATION=...`,
   chạy `docker compose -f dong_goi/docker-compose.prod.yml up -d`, rồi bấm **Xác minh**.
3. Mục **Sơ đồ trang web**: gửi `sitemap.xml`.

Máy chủ tự chèn vào mọi trang:

- Thẻ `canonical`, Open Graph (xem trước đẹp khi chia sẻ Facebook/Zalo) và dữ liệu có cấu trúc JSON-LD (WebSite, Dataset).
- `noindex` cho trang đăng nhập và trang quản trị.
- `robots.txt` và `sitemap.xml` tự sinh.

Google thường lập chỉ mục sau vài ngày đến vài tuần.

## Bước 9 — App Android dùng máy chủ Internet

Trên máy Windows, ghi `TEN_MIEN=<tên-miền>` vào `.env` rồi:

```powershell
cd mobile; npm run apk      # tạo mobile\AirHCM.apk, app tự thử https://<tên-miền> đầu tiên
```

Cài APK lên điện thoại. App kết nối được qua 4G và **tự kiểm tra AQI mỗi 30 phút kể cả khi đã đóng app** (cảnh báo bằng thông báo Android).
Nhớ cho phép thông báo khi app hỏi. Nếu máy tắt cảnh báo nền để tiết kiệm pin: vào Cài đặt → Ứng dụng → AirHCM → Pin → *Không hạn chế*.

Người dùng trình duyệt (kể cả iPhone đã "Thêm vào MH chính") bật **thông báo nền** ở trang *Tài khoản & bảo mật*.

## Vận hành hằng ngày

| Việc | Lệnh (trên máy chủ, trong thư mục AirHCM) |
|---|---|
| Xem nhật ký | `docker compose -f dong_goi/docker-compose.prod.yml logs -f --tail 100 backend` |
| Trạng thái dịch vụ | `docker compose -f dong_goi/docker-compose.prod.yml ps` |
| Cập nhật mã mới | chép zip mới lên, giải nén đè, `bash dong_goi/trien_khai/cap_nhat.sh` (tự sao lưu CSDL trước) |
| Sao lưu | tự động 02:30 mỗi ngày vào `sao_luu/` (giữ 14 bản); tải về: `scp ubuntu@IP:~/AirHCM/sao_luu/*.gz .` |
| Khôi phục bản sao lưu | `bash dong_goi/trien_khai/khoi_phuc.sh sao_luu/airhcm_<ngày>.sql.gz --ghi-de` |
| Khởi động lại | `docker compose -f dong_goi/docker-compose.prod.yml restart backend` |

- Máy chủ tự khởi động lại sau sự cố hoặc khi máy ảo khởi động lại (`restart: always`).
- Đồng bộ dữ liệu hằng ngày chạy **bên trong máy chủ** (`DONG_BO_BAT=1`, giờ đặt ở `DONG_BO_GIO`), không cần Windows Task Scheduler nữa.

## Gỡ lỗi thường gặp

| Hiện tượng | Nguyên nhân / cách sửa |
|---|---|
| Trình duyệt báo lỗi chứng chỉ, Caddy log `challenge failed` | Tên miền chưa trỏ đúng IP (bước 3), hoặc chưa mở cổng 80/443 (bước 2). Sửa xong: `docker compose ... restart caddy` |
| Không vào được web từ ngoài | Kiểm tra Security List (bước 2); trên máy chủ: `curl -I https://<tên-miền>` phải ra `HTTP/2 301` hoặc `200` |
| `backend` khởi động lại liên tục | `docker compose ... logs backend`: thường do thiếu `JWT_SECRET_KEY` hoặc sai `DB_PASS` trong `.env` |
| Không gửi được email OTP | Điền `SMTP_USER`, `SMTP_PASS` (mật khẩu ứng dụng Gmail 16 ký tự) trong `.env`, rồi `up -d` |
| Hết RAM khi build | Script đã tạo swap 2 GB; với máy AMD 1 GB RAM nên chọn máy ARM A1 thay thế |
