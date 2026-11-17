# Bật đăng nhập / đăng ký bằng Google, Facebook, Zalo

Mã nguồn đã sẵn sàng. Mỗi nhà cung cấp chỉ cần **2 khóa** điền vào `.env`; nút đăng nhập tương ứng tự hiện trên trang `login.html`.
Nhà cung cấp nào chưa có khóa thì nút đó không hiện (không lỗi).

**Địa chỉ chuyển hướng (Redirect URI)** phải khai báo **y hệt** ở trang nhà phát triển. `<web>` là địa chỉ bạn mở AirHCM:

| Nhà cung cấp | Redirect URI |
|---|---|
| Google | `<web>/api/v1/auth/oauth/google/callback` |
| Facebook | `<web>/api/v1/auth/oauth/facebook/callback` |
| Zalo | `<web>/api/v1/auth/oauth/zalo/callback` |

`<web>` = `http://localhost:8000` khi chạy trên máy, hoặc `https://<tên-miền>` khi đã triển khai (docs/TRIEN_KHAI_ORACLE.md).
Nên khai báo cả hai. Lưu ý: Facebook và Zalo thường chỉ chấp nhận **HTTPS**, nên dùng chúng sau khi đã có tên miền.

---

## 1. Google (khoảng 10 phút, miễn phí)

1. Vào https://console.cloud.google.com, tạo dự án mới (vd. `AirHCM`).
2. **APIs & Services → OAuth consent screen** (Google Auth Platform):
   - User type: **External**. Tên ứng dụng: `AirHCM`, email hỗ trợ: email của bạn.
   - Trang chủ: `<web>/tong-quan.html` · Chính sách quyền riêng tư: `<web>/chinh-sach-rieng-tu.html`.
   - Phạm vi (scopes): chỉ cần `openid`, `email`, `profile`. Đây là phạm vi cơ bản nên **không cần Google thẩm định**.
   - Khi đang thử: thêm email của bạn vào **Test users**. Muốn mọi người dùng được: bấm **Publish app**.
3. **Credentials → Create credentials → OAuth client ID** → loại **Web application**:
   - Authorized redirect URIs: thêm `http://localhost:8000/api/v1/auth/oauth/google/callback` (và bản `https://<tên-miền>/...`).
4. Chép **Client ID** và **Client secret** vào `.env`:
   ```
   GOOGLE_CLIENT_ID=xxxxxxxx.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxx
   ```

## 2. Facebook (khoảng 15 phút, miễn phí)

1. Vào https://developers.facebook.com → **My Apps → Create App**.
   Trường hợp sử dụng: **Authenticate and request data from users with Facebook Login**.
2. **Use cases → Facebook Login → Customize → Settings**:
   - Valid OAuth Redirect URIs: `https://<tên-miền>/api/v1/auth/oauth/facebook/callback`
     (khi ứng dụng ở chế độ Development, Facebook tự cho phép `http://localhost`).
   - Quyền `email` và `public_profile` có sẵn, không cần xét duyệt.
3. **App settings → Basic**:
   - Privacy Policy URL: `<web>/chinh-sach-rieng-tu.html`
   - User data deletion → Data deletion instructions URL: `<web>/chinh-sach-rieng-tu.html#xoa-du-lieu`
   - Chép **App ID** và **App secret**.
4. Chuyển ứng dụng sang **Live** (công tắc ở đầu trang). Ở chế độ Development chỉ tài khoản quản trị/tester của ứng dụng đăng nhập được.
5. Điền `.env`:
   ```
   FACEBOOK_APP_ID=1234567890
   FACEBOOK_APP_SECRET=xxxxxxxx
   ```

## 3. Zalo (khoảng 15 phút, miễn phí)

1. Vào https://developers.zalo.me → đăng nhập bằng Zalo → **Thêm ứng dụng mới** (tên `AirHCM`, danh mục Tiện ích/Giáo dục).
2. Trong ứng dụng → **Sản phẩm → Đăng nhập** (Social API / Zalo Login) → **Cài đặt**:
   - Thêm **Callback URL**: `https://<tên-miền>/api/v1/auth/oauth/zalo/callback`.
   - Làm theo hướng dẫn **xác thực tên miền** của Zalo (thường là đặt tệp hoặc thẻ meta lên web; gửi tệp đó cho mình
     hoặc chép vào thư mục `frontend/`).
3. **Cài đặt ứng dụng**: chép **ID ứng dụng** và **Khóa bí mật của ứng dụng**; kích hoạt ứng dụng.
4. Điền `.env`:
   ```
   ZALO_APP_ID=1234567890123456789
   ZALO_APP_SECRET=xxxxxxxx
   ```

Zalo **không cung cấp email**. Tài khoản tạo bằng Zalo có định danh nội bộ, đăng nhập lại bằng Zalo, và có thể đặt thêm mật khẩu ở trang Tài khoản.

---

## Sau khi điền khóa

Khởi động lại máy chủ, mở `login.html`: các nút **Đăng nhập bằng Google / Facebook / Zalo** sẽ hiện.
Trên máy chủ Docker: `docker compose -f dong_goi/docker-compose.prod.yml up -d`.

## Cách hệ thống xử lý (để trình bày)

| Tình huống | Hệ thống làm gì |
|---|---|
| Lần đầu đăng nhập bằng mạng xã hội | Tự **tạo tài khoản** (vai trò người xem; admin nếu email đã xác minh nằm trong `ADMIN_EMAILS`) |
| Email đã được Google/Facebook **xác minh** trùng tài khoản có sẵn | Tự **gộp** vào tài khoản đó |
| Email **chưa xác minh** trùng tài khoản có sẵn | **Không gộp** (chống chiếm tài khoản), tạo tài khoản riêng |
| Tài khoản đã bật xác thực 2 lớp | Vẫn phải **nhập mã 6 số** sau khi đăng nhập bằng mạng xã hội |
| Đang đăng nhập, bấm *Liên kết* ở trang Tài khoản | Gắn thêm cách đăng nhập vào tài khoản hiện tại |
| Gỡ liên kết cuối cùng của tài khoản chưa có mật khẩu | Bị chặn (tránh mất quyền vào tài khoản); đặt mật khẩu trước |

Bảo mật theo chuẩn OAuth 2.0:

- Luồng Authorization Code + **PKCE (S256)**.
- `state` ngẫu nhiên lưu trong cookie HttpOnly ký số, hiệu lực 10 phút, chống CSRF đăng nhập.
- Hồ sơ người dùng chỉ đọc từ máy chủ nhà cung cấp; Facebook gọi kèm `appsecret_proof`.
- Chỉ chuyển hướng về trang nội bộ.
- Mọi sự kiện được ghi nhật ký.

Kiểm thử tự động: `tests/test_bao_mat.py` (giả lập máy chủ nhà cung cấp).
