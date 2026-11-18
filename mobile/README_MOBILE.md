# App di động AirHCM (Android) — v2

## Các tệp trong thư mục này
| Tệp | Là gì |
|---|---|
| `AirHCM.apk` | **Tệp cài app Android**: chép sang điện thoại rồi mở để cài (hoặc tải ở https://airhcmcity.asia/tai-app.html) |
| `build_apk.js` | Tạo lại APK: `npm run apk` (lấy tên miền từ `TEN_MIEN` trong `.env`) |
| `chay_may_ao.js` | Mở máy ảo Android, cài và chạy app: `npm run may-ao` |
| `package.json`, `package-lock.json` | Danh sách thư viện Node.js của app (Capacitor); `npm install` đọc tệp này |
| `capacitor.config.json` | Cấu hình app: tên, mã gói `vn.edu.aqi.hcm`, tác vụ nền kiểm tra AQI mỗi 30 phút |
| `www/` | Trang khởi động trong app (dò máy chủ) và `may_chu.js` (địa chỉ máy chủ, tự sinh khi build) |
| `android/` | Dự án Android do Capacitor tạo — không cần sửa tay |

## Cách hoạt động
APK chỉ chứa một **trang khởi động** nhỏ (`www/index.html`). Khi mở app, trang này tự dò máy chủ theo thứ tự:
0. máy chủ công khai `https://airhcmcity.asia` (ghi vào `www/may_chu.js` lúc build),
1. máy chủ đã dùng lần trước,
2. `http://10.0.2.2:8000` — địa chỉ máy tính khi chạy trong **máy ảo Android**,
3. `http://192.168.1.227:8000` — IP Wi-Fi của máy tính lúc build (sửa mảng `MAC_DINH` trong `www/index.html` nếu đổi).

Tìm thấy thì app mở thẳng web từ máy chủ. Vì app và máy chủ **cùng nguồn**, đăng nhập (cookie `SameSite=Strict`) và mọi trang chạy như trên trình duyệt. Giao diện luôn là bản mới nhất trên máy chủ, sửa web **không cần build lại APK**. Không tìm thấy máy chủ thì app hiện ô nhập địa chỉ. Đổi máy chủ sau này: menu **Thêm → Hệ thống → Đổi máy chủ (app)**.

## Một APK dùng cho cả máy ảo và điện thoại thật
Tệp: `mobile/AirHCM.apk` (bản debug, khoảng 4 MB).

| | Máy ảo Android | Điện thoại thật |
|---|---|---|
| Chạy backend | như bình thường (`uvicorn main:app`) | `chay_server_dien_thoai.bat` ở thư mục gốc (nghe trên mạng Wi-Fi) |
| Kết nối | tự dùng `10.0.2.2:8000` | điện thoại **cùng Wi-Fi** với máy tính; app tự thử IP mặc định hoặc nhập IP Wi-Fi (bat in ra sẵn, chọn dòng `192.168.1.x`) |
| Cài app | `npm run may-ao` (mở máy ảo, cài, chạy) | cắm cáp + bật *Gỡ lỗi USB* rồi `npm run may-ao`, **hoặc** chép `AirHCM.apk` sang điện thoại và mở để cài (cho phép "cài ứng dụng không rõ nguồn") |
| Tường lửa | không cần | lần đầu, mở CMD **quyền Administrator**: `netsh advfirewall firewall add rule name="AirHCM 8000" dir=in action=allow protocol=TCP localport=8000 profile=private` |

## Build lại APK
Cần: Node.js 18+, JDK 21+ (máy đang có JDK 23), Android SDK (`%LOCALAPPDATA%\Android\Sdk`, không bắt buộc mở Android Studio).
```
cd mobile
npm install          # lần đầu
npm run apk          # → mobile/AirHCM.apk
npm run may-ao       # cài + mở trên máy ảo (hoặc điện thoại đang cắm cáp)
```
Chỉ cần build lại khi đổi `www/` (trang khởi động), `capacitor.config.json`, tên/biểu tượng app. Biểu tượng tạo từ `assets/` bằng `npx @capacitor/assets generate --android`.

## Web và PWA
- Máy tính: `http://localhost:8000`.
- Điện thoại mở bằng trình duyệt: chạy `chay_server_dien_thoai.bat`, mở `http://<IP Wi-Fi>:8000`. Giao diện tự chuyển sang dạng điện thoại (thanh tab dưới đáy).
- Cài PWA "Thêm vào màn hình chính" trên điện thoại cần **HTTPS** (triển khai lên máy chủ thật, hoặc đường hầm `cloudflared tunnel --url http://localhost:8000`).

## Giới hạn
- Bản debug, chưa ký phát hành; đưa lên Google Play cần build `assembleRelease` với khóa ký riêng.
- App cần mạng tới máy chủ (dữ liệu nằm ở máy chủ); mất kết nối thì hiện trang `www/loi.html` có nút Thử lại / Đổi máy chủ.
- Đi qua HTTP trong mạng nội bộ (`cleartext`); khi triển khai thật nên dùng HTTPS.
- Chưa có thông báo đẩy; cảnh báo vẫn gửi qua email.
