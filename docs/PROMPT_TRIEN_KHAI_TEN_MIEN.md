# Prompt: đưa web đang chạy trên máy cá nhân lên Internet bằng tên miền riêng + Cloudflare Tunnel + Google Search Console

> Cách dùng: sửa 4 dòng trong khối **THÔNG TIN CỦA TÔI**, rồi dán toàn bộ phần bên dưới đường kẻ vào trợ lý AI lập trình
> (Claude Code, Cursor…) đang mở trong thư mục dự án. Chi phí: chỉ tiền tên miền (khoảng 25.000–60.000 ₫ năm đầu).
> Giới hạn: web chỉ truy cập được khi máy tính đang bật và chạy máy chủ.

---

Bạn là trợ lý triển khai. Hãy giúp tôi đưa web đang chạy trên máy cá nhân ra Internet với **tên miền riêng, HTTPS, link cố định**,
dùng **Cloudflare Tunnel** (miễn phí, không cần mở cổng router, không cần thuê máy chủ), rồi đăng ký **Google Search Console** để làm SEO.

## THÔNG TIN CỦA TÔI
- Tên miền muốn mua (hoặc đã mua): `TEN-MIEN-CUA-BAN.xyz`
- Nhà đăng ký tên miền: `PA Vietnam / Mắt Bão / iNET / Tenten / Porkbun…`
- Web chạy ở máy tôi tại: `http://127.0.0.1:8000` (lệnh khởi động: `…`)
- Hệ điều hành: `Windows 11` (hoặc macOS / Linux)

## QUY TẮC LÀM VIỆC
1. Làm **từng bước một**. Hết mỗi bước, **tự kiểm tra bằng lệnh** (curl, DNS-over-HTTPS) rồi mới sang bước sau. Báo rõ đã kiểm chứng gì, chưa kiểm chứng gì.
2. Việc cần đăng nhập / thanh toán / bấm trên web (nhà đăng ký, Cloudflare, Google) thì **hướng dẫn tôi làm**, ghi rõ tên nút và nên chọn gì.
   Mọi việc chạy được bằng lệnh trên máy thì **bạn tự làm**.
3. **Bảo mật:** không in ra mật khẩu, khóa API, tệp `.env`, tệp khóa của đường hầm (`~/.cloudflared/*.json`, `cert.pem`).
   Nhắc tôi **không** gửi ảnh chụp có mật khẩu, mã QR 2FA, mã bảo mật, số thẻ. Không đưa khóa vào git.
4. Trước khi sửa mã nguồn, đọc mã liên quan và chạy lại kiểm thử sau khi sửa.

## BƯỚC 1 — Mua tên miền (tôi làm, bạn hướng dẫn)
- Chọn đuôi rẻ: `.xyz .site .online .asia .click`. Tránh `.vn` (phải nộp giấy tờ, đắt hơn), tránh `.com` nếu giá khuyến mãi bắt mua nhiều năm.
- Nhắc tôi đọc **dòng chữ nhỏ**: giá năm đầu có kèm điều kiện "thời hạn 2–3 năm" không, **giá gia hạn** năm sau bao nhiêu.
  Chọn **thời hạn 1 năm**, xem **tổng tiền trong giỏ hàng** (không tin giá quảng cáo).
- **Bỏ hết dịch vụ kèm theo**, kể cả loại "0 đ năm đầu": DNSSEC, Email, Hosting, SSL, Page Builder, bảo vệ thông tin.
  Đặc biệt **không bật DNSSEC** ở nhà đăng ký (sẽ làm hỏng việc chuyển sang Cloudflare).
- Thông tin chủ thể: cá nhân, đúng sự thật. Tắt **tự động gia hạn** nếu chỉ dùng 1 năm.
- Tên miền đã mua **không đổi tên được**; tên miền con (`app.`, `demo.`) thì tạo miễn phí, không giới hạn.

## BƯỚC 2 — Đưa tên miền về Cloudflare (tôi làm, bạn hướng dẫn và kiểm tra)
1. Tạo tài khoản miễn phí tại https://dash.cloudflare.com/sign-up, chọn **Add a domain**, nhập tên miền, chọn gói **Free**.
2. Phần chính sách bot: **Search = Allow** (bắt buộc để Google tìm thấy web), Training tùy tôi, Agents nên Allow,
   **tắt "Bot Preference Sync"** nếu web đã có `robots.txt` riêng.
3. Trang DNS records: **không thêm bản ghi nào** (đường hầm sẽ tự tạo). Nếu Cloudflare cảnh báo "Without DNS records…", chọn **Add records later**.
4. Cloudflare cấp 2 nameserver dạng `xxx.ns.cloudflare.com`. Hướng dẫn tôi vào trang quản lý tên miền ở nhà đăng ký
   (thường là: tài khoản → Quản lý dịch vụ → tên miền → Cấu hình DNS → **Thay đổi DNS / Nameserver**), **xóa hết nameserver cũ**, điền 2 nameserver Cloudflare, lưu.
   Nếu ô cũ bị khóa: tìm nút xóa ở cột bên phải (kéo thanh cuộn ngang) hoặc nhờ hỗ trợ của nhà đăng ký.
   Cảnh báo kiểu "cấu hình chưa có hiệu lực vì không dùng DNS của chúng tôi" là **dấu hiệu đã đổi thành công**: không bấm "đổi lại nameserver mặc định".
5. **Bạn kiểm tra** việc chuyển bằng DNS-over-HTTPS (không phụ thuộc DNS máy):
   `curl -s "https://dns.google/resolve?name=TEN-MIEN&type=NS"`. Kết quả có `cloudflare.com` là xong.
   Lỗi "lame delegation / REFUSED" từ IP của nhà đăng ký = đang chờ cập nhật (15 phút đến vài giờ). Có thể chạy vòng lặp nền kiểm tra mỗi 2 phút.

## BƯỚC 3 — Tạo đường hầm cố định (bạn làm)
1. Cài `cloudflared` (Windows: `winget install --id Cloudflare.cloudflared -e`; macOS: `brew install cloudflared`).
2. `cloudflared tunnel login` (chạy nền; trình duyệt mở ra, tôi chọn tên miền rồi bấm **Authorize**; nếu không tự mở, lấy link trong log đưa tôi).
3. `cloudflared tunnel create <ten-duong-ham>` rồi viết `~/.cloudflared/config.yml`:
   ```yaml
   tunnel: <ID>
   credentials-file: C:/Users/<user>/.cloudflared/<ID>.json   # Windows: dùng dấu / , KHÔNG dùng \ trong heredoc
   ingress:
     - hostname: TEN-MIEN
       service: http://127.0.0.1:8000
     - hostname: www.TEN-MIEN
       service: http://127.0.0.1:8000
     - service: http_status:404
   ```
   Chạy `cloudflared tunnel ingress validate`, rồi `cloudflared tunnel route dns <ten-duong-ham> TEN-MIEN` và tương tự cho `www.TEN-MIEN`.
4. Bật máy chủ web, chạy `cloudflared tunnel --no-autoupdate run <ten-duong-ham>`, rồi **kiểm tra**: `curl -I https://TEN-MIEN/` phải ra 200/301.
   Lỗi `530 / error 1033` = đường hầm chưa chạy (xem log, thường do sai đường dẫn `credentials-file`).
5. Tạo tệp bấm đúp (Windows `.bat` lưu **CRLF**; macOS/Linux `.sh`) để: tự bật máy chủ nếu chưa chạy, rồi chạy đường hầm, in link công khai.
   Nếu chưa có `config.yml` thì dùng đường hầm tạm `cloudflared tunnel --url http://127.0.0.1:8000` (link `*.trycloudflare.com` đổi mỗi lần chạy).

## BƯỚC 4 — Kiểm tra mã nguồn chạy đúng sau proxy HTTPS (bạn làm)
- Ứng dụng nhận yêu cầu qua proxy: bảo đảm nó **tin header X-Forwarded-Proto từ 127.0.0.1** (uvicorn mặc định có `--proxy-headers`,
  `forwarded-allow-ips=127.0.0.1`), để biết là HTTPS (cookie `Secure`, HSTS).
- Kiểm tra chống CSRF theo Origin: thử `POST` đăng nhập với `Origin: https://TEN-MIEN` phải ra lỗi xác thực bình thường (401), **không** phải 403 "sai nguồn gốc".
- Địa chỉ trả về OAuth nên **lấy theo host của yêu cầu** để cả `localhost` và tên miền cùng chạy. Nếu đặt cứng một biến "địa chỉ công khai" thì đăng nhập trên localhost sẽ hỏng.
- `sitemap.xml`, `robots.txt`, thẻ `canonical` phải dùng đúng `https://TEN-MIEN/…`. Kiểm tra bằng curl.
- Nếu app di động/PWA có service worker: tăng phiên bản cache để máy người dùng tải giao diện mới.

## BƯỚC 5 — Đăng nhập Google (nếu web có "Đăng nhập bằng Google")
Hướng dẫn tôi vào https://console.cloud.google.com/apis/credentials, **đúng project** chứa OAuth client đang dùng (đối chiếu Client ID với `.env`, không in secret):
- **Authorized JavaScript origins:** `https://TEN-MIEN`, `https://www.TEN-MIEN`
- **Authorized redirect URIs:** thêm bản `https://TEN-MIEN/...callback` và `https://www.TEN-MIEN/...callback`, **giữ** bản localhost.
- **Branding:** trang chủ `https://TEN-MIEN`, chính sách riêng tư `https://TEN-MIEN/<trang-chinh-sach>`, authorized domain `TEN-MIEN`.
- **Audience:** Publish app (hoặc thêm Test users). Chờ khoảng 5 phút mới có hiệu lực.
- Lưu ý: từ 11/2026 Google Cloud bắt bật **xác minh 2 bước** cho tài khoản mới vào được console.

## BƯỚC 6 — Google Search Console (tôi làm, bạn hướng dẫn và kiểm tra)
1. https://search.google.com/search-console → **Add a website** → chọn **Domain** (ô trái), nhập `TEN-MIEN` (không `https://`, không `www`).
2. Xác minh: thử **Start verification** với Cloudflare. Nếu báo **401 Unauthorized**: đổi "Instructions for" sang **Any DNS provider**,
   chép chuỗi `google-site-verification=…`, thêm bản ghi **TXT**, Name `@`, trong Cloudflare DNS, rồi bấm **Verify**.
   **Không xóa** 2 bản ghi CNAME của đường hầm, **không xóa** bản ghi TXT sau khi xác minh.
   Bạn kiểm tra TXT: `curl -s "https://dns.google/resolve?name=TEN-MIEN&type=TXT"`.
3. **Sitemaps:** với tài sản kiểu Domain phải nhập **địa chỉ đầy đủ** `https://TEN-MIEN/sitemap.xml` → Send.
   "Couldn't fetch" lúc đầu là bình thường nếu máy đang tắt; bật máy rồi chờ.
4. **Kiểm tra URL** → **Yêu cầu lập chỉ mục** cho 3–5 trang quan trọng nhất (giới hạn khoảng 10 lần/ngày).
5. Sau 3–14 ngày: tìm `site:TEN-MIEN` trên Google; chụp màn hình Sitemaps "Success", Pages, Performance làm minh chứng.

## BƯỚC 7 — Báo cáo cuối
Kết thúc, liệt kê cho tôi:
- Các địa chỉ đã kiểm tra bằng curl và mã trả về.
- Cách bật web lần sau (tệp bấm đúp), cách tắt.
- Những gì **chưa** kiểm chứng (ví dụ: điện thoại thật, đăng nhập Google sau khi lưu URI).
- Giới hạn cần nói thật với người xem (ví dụ giảng viên): web chỉ chạy khi máy bật; muốn 24/7 cần máy chủ (Oracle Always Free,
  Google Cloud có 300 USD dùng thử nhưng một số thẻ Việt Nam bị yêu cầu trả trước khoảng 800.000 ₫).

## Lỗi đã gặp và cách xử lý nhanh
| Hiện tượng | Nguyên nhân / cách sửa |
|---|---|
| `redirect_uri_mismatch` khi đăng nhập Google | Chưa khai báo đúng redirect URI cho tên miền / link tạm; link `trycloudflare` đổi mỗi lần nên phải khai lại |
| Máy chủ Python chết ngay khi khởi động: `UnicodeEncodeError cp1258` | Chạy với UTF-8: `python -X utf8 …` hoặc `chcp 65001` trước |
| `530` / `error code: 1033` | Đường hầm không chạy; xem log `cloudflared` (hay gặp: sai đường dẫn credentials trên Windows) |
| Search Console báo 401 khi Authorize Cloudflare | Dùng cách thêm TXT thủ công |
| Nhà đăng ký không cho xóa nameserver cũ | Tìm nút xóa ở cột ẩn bên phải bảng, hoặc gửi yêu cầu hỗ trợ |
| Ảnh chụp màn hình lộ mật khẩu / mã 2FA | Đổi mật khẩu; với 2FA bấm "Đổi mã bảo mật" trước khi quét QR |
