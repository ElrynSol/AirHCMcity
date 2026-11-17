# Hệ thống Giám sát, Quản lý & Dự báo Chất lượng Không khí TP.HCM

Đồ án chuyên ngành · Lê Ngọc Ánh Dương (MSSV 1250080037) · GVHD: TS. Dương Thị Thúy Nga

## Dữ liệu (trung thực về bản chất)
| Chỉ số | Nguồn | Bản chất |
|---|---|---|
| PM2.5, PM10, O₃, thời tiết | Open-Meteo (mô hình CAMS toàn cầu), lưới ~0,4° ≈ 45 km | Mô hình, chưa kiểm chứng đo đạc mặt đất |
| NO₂, CO, SO₂ | Sentinel-5P qua Google Earth Engine | Cột khí vệ tinh (mol/m²), trễ 2–3 tuần |
| Giá trị theo trạm / phường-xã | Hiệu chỉnh không gian + nội suy IDW | Ước tính |

AQI tính theo VN_AQI — QĐ 1459/QĐ-TCMT (bảng ngưỡng, 6 mức màu, khuyến nghị sức khỏe) từ PM2.5, PM10, O₃; ngưỡng so sánh nồng độ theo QCVN 05:2023/BTNMT. Xem trang **Dữ liệu** trên web để biết tình trạng cập nhật.

## Kiến trúc
```
Nguồn dữ liệu (Open-Meteo, GEE) → script nạp (download_*, load_to_db, dong_bo_hang_ngay)
        → PostgreSQL/PostGIS → FastAPI (backend/) → Web tĩnh (frontend/, Leaflet + Chart.js)
                                  ↘ cảnh báo email (dịch vụ nền) ↘ mô hình Random Forest (models/)
```
```
backend/        API FastAPI: main.py · core/ (cấu hình, bảo mật, mail, nhật ký, bus sự kiện) · routers/ · services/
frontend/       17 trang web + nav.js, style.css, tro-ly.js, sw.js (PWA)
ml/             tinh_aqi, predict, train_model, train_du_bao_gio, train_diem, train_downscale_model, phan_cum_tram
models/         mô hình đã huấn luyện (.pkl, .joblib) + chỉ số đánh giá (.json)
data_pipeline/  download_*, gee_extract, run_pipeline, load_to_db, dong_bo_hang_ngay, kiem_tra_du_lieu, doi_chieu_tram_that
iot/            ESP32 Wokwi (trạm cảm biến, bảng điện tử) + giả lập Python
mobile/         app Android (Capacitor) + AirHCM.apk
tests/          127 kiểm thử pytest
dong_goi/       Dockerfile, docker-compose.yml, tao_ban_nop.py (tạo bản nộp .zip sạch)
docs/           CAU_TRUC_DU_AN.md (giải thích từng thư mục, từng tệp)
```
Chi tiết chức năng từng tệp: [docs/CAU_TRUC_DU_AN.md](docs/CAU_TRUC_DU_AN.md). Tạo bản nộp: `python dong_goi/tao_ban_nop.py`.

## Chạy
Chọn 1 trong 3 cách (chi tiết từng tệp: `docs/CAU_TRUC_DU_AN.md`):

| Cách | Hệ điều hành | Lệnh |
|---|---|---|
| Cài trực tiếp | Windows | Chuột phải `cai_dat.ps1` → *Run with PowerShell*, rồi bấm đúp `chay_server.bat` |
| Cài trực tiếp | Linux / macOS | `bash cai_dat.sh` rồi `bash chay_server.sh` |
| Docker (không cần cài Python, PostgreSQL) | Mọi hệ điều hành, x86-64 hoặc ARM64 | `docker compose -f dong_goi/docker-compose.yml up -d --build` |

Mở `http://localhost:8000`. Kiểm tra máy có đủ điều kiện chạy (Python, thư viện, RAM, ổ đĩa, cổng, CSDL, mô hình):
`python dong_goi/kiem_tra_moi_truong.py`. Lên Internet 24/7 (HTTPS, tên miền, máy tắt vẫn chạy): **`docs/TRIEN_KHAI_ORACLE.md`**.

## Bảo mật (đăng nhập chuẩn doanh nghiệp, OWASP ASVS mức 2)
- Mật khẩu băm **Argon2id** (hash bcrypt cũ tự nâng cấp khi đăng nhập); chính sách ≥ 10 ký tự, có chữ và số, chặn mật khẩu phổ biến/chứa tên, email.
- **Phiên phía máy chủ**: cookie `HttpOnly; SameSite=Strict; Secure` chứa JWT có mã phiên. Đăng xuất, đổi/đặt lại mật khẩu thì **thu hồi ngay**.
  Phiên tự hết sau 2 giờ không hoạt động. Xem và đăng xuất từng thiết bị ở trang *Tài khoản & bảo mật*.
- **Đăng nhập / đăng ký bằng Google, Facebook, Zalo** (OAuth 2.0 + PKCE; tự gộp tài khoản chỉ khi email đã được xác minh) — bật bằng khóa trong `.env`, hướng dẫn: `docs/DANG_NHAP_MXH.md`.
- **Xác thực 2 lớp TOTP** (Google/Microsoft Authenticator) kèm 8 mã dự phòng dùng 1 lần; bí mật lưu mã hóa; chống dùng lại mã.
- Chống dò mật khẩu: khóa theo (email, IP) và theo email trên mọi IP; giới hạn tần suất đăng ký, OTP, mã 2 lớp.
  Quên mật khẩu không lộ email nào đã đăng ký; OTP chỉ lưu bản băm, tự hủy sau 5 lần sai.
- Header bảo mật (CSP, chống iframe, HSTS…), chống CSRF bằng kiểm tra Origin; dữ liệu cá nhân không lưu cache/offline; mọi sự kiện bảo mật ghi nhật ký.
- Quyền admin qua `ADMIN_EMAILS`; không đưa `.env`, `gee-key.json`, `backup.sql`, `bi_mat/` lên kho mã hoặc bản nộp.

## Giới hạn đã biết
- Chưa đối chiếu với trạm đo mặt đất; giá trị theo trạm/phường-xã là ước tính.
- Dự báo theo ngày (Random Forest) chưa chứng minh được là hơn cách đoán “ngày mai = hôm nay” (xem mục dưới); dự báo theo giờ mới có kỹ năng được kiểm chứng.
- Hệ thống phục vụ học thuật, không thay thế số liệu công bố chính thức.

## Kiến trúc hướng sự kiện (gọn) và nhật ký tập trung

- `core/logbus.py`: mọi thành phần ghi nhật ký về bảng `nhat_ky_he_thong` (giữ 90 ngày). Admin xem ở trang **Nhật ký** (`nhat-ky.html`).
- `core/events.py`: bus sự kiện nội bộ publish/subscribe (thay Kafka ở quy mô đồ án).
- `services/cdc.py`: trigger PostgreSQL + `LISTEN/NOTIFY`. Thêm/sửa/xóa trạm (kể cả sửa trực tiếp trong pgAdmin) → `tram.da_tao/da_sua/da_xoa`; có dữ liệu mới vào `du_lieu_tram_mat_dat` → `du_lieu.da_nap`.
- Luồng cảnh báo: `du_lieu.da_nap` → gom 20 giây → tính AQI → `aqi.vuot_nguong` → gửi email (tối đa 1 thư/ngày/đăng ký, không gửi trùng). Vòng quét 6 giờ là lưới an toàn.
- Sơ đồ: `kien_truc_hien_tai.svg/png`, `kien_truc_mo_rong.svg/png` (Kafka, hướng phát triển, chưa triển khai).

## Trình diễn luồng cảnh báo (admin)
Trang `luong-canh-bao.html` (mở từ trang Nhật ký): chạy từng giai đoạn đọc dữ liệu → tính AQI → so ngưỡng → sự kiện → soạn thư → gửi, và xem **Hộp thư đã gửi** (bảng `thu_da_gui`) ngay trên web, không cần mở hộp thư. Chế độ này không bị giới hạn 1 thư/ngày và không đổi trạng thái đăng ký của người dùng thật.

## Dự báo PM2.5 theo giờ (24 giờ tới)
- Huấn luyện: `python ml/train_du_bao_gio.py` (từ thư mục gốc). Ghi `models/du_bao_gio.joblib` và `models/du_bao_gio_chi_so.json`.
- API: `GET /api/v1/du-bao-gio` (dự báo + khung giờ tốt/xấu + so ngưỡng WHO/QCVN), `GET /api/v1/du-bao-gio/chi-so` (số liệu đánh giá).
- Đánh giá theo thứ tự thời gian, luôn so với mô hình nền "giữ nguyên" (persistence) và "hôm qua cùng giờ"; báo cáo "kỹ năng" thay vì chỉ R².
- Dữ liệu gốc là số liệu mô hình CAMS/ERA5 qua Open-Meteo, không phải đo đạc mặt đất.

## Dự báo PM2.5 theo ngày: kết quả đánh giá trung thực (v3.7)
- Huấn luyện: `python ml/train_model.py` (từ thư mục gốc). Hai mô hình, phải gọi đúng tên:
  - **Ước lượng trong ngày**: dùng NO₂/CO/SO₂/O₃ và thời tiết của chính ngày đó → KHÔNG phải dự báo trước.
  - **Dự báo ngày mai** (`models/random_forest_pm25_du_bao.pkl`): chỉ dùng PM2.5 các ngày trước + lịch. Đây là mô hình `predict.py` và trang Dự báo đang dùng.
- Đánh giá: chia theo thời gian, so với nền “hôm nay = hôm qua”, kiểm chéo cuốn chiếu 5 lần, kỹ năng theo mùa, khoảng tin cậy 95% bootstrap theo khối 7 ngày.
- Kết quả trên dữ liệu 08/2022–10/2026 (kỹ năng = 1 − RMSE_mô_hình / RMSE_nền):
  - Dự báo ngày mai: kỹ năng gộp +2,3% (95% CI −2,7% … +7,1%); mùa mưa −0,3%, mùa khô +6,0% → **chưa chứng minh được hơn nền**.
  - Ước lượng trong ngày: kỹ năng gộp +13,4% (95% CI +3,4% … +20,0%).
  - R² của mô hình dự báo ≈ 0,67 so với 0,65 của nền: R² cao chủ yếu do PM2.5 hôm nay giống hôm qua.
- `predict.py` từ chối dự báo khi dữ liệu CSDL cũ quá 1 ngày hoặc thiếu ngày trong 7 ngày gần nhất; khoảng dự báo là phân vị 10–90% của sai số thực; dự báo nhiều ngày chỉ có ngày đầu được kiểm chứng.
- Dự báo theo phường/xã hiện trả giá trị cấp thành phố (mô hình chưa có thông tin riêng từng khu vực).
- Chưa đối chiếu với trạm đo mặt đất: dùng `data_pipeline/doi_chieu_tram_that.py` với CSV số đo thật.
- Kiểm tra chất lượng dữ liệu: `python data_pipeline/kiem_tra_du_lieu.py --cot-tram tram_id`.

## v4.1 — Chuẩn hóa theo VN_AQI (QĐ 1459/QĐ-TCMT)
- `ml/tinh_aqi.py`: bảng ngưỡng đầy đủ 7 khoảng của QĐ 1459 cho PM2.5, PM10, O₃ (1h và 8h), kèm NO₂/SO₂/CO (µg/m³, chỉ dùng khi có số đo mặt đất). Sửa ngưỡng PM10 (51–100 ↔ 50–150 µg/m³) và O₃ trước đây lệch chuẩn. AQI chỉ tính khi có PM2.5 hoặc PM10 (theo QĐ 1459). O₃ trung bình ngày/8h tra bảng 8h, vượt 400 µg/m³ chuyển sang bảng 1h.
- 6 mức + 6 màu chuẩn (#00E400, #FFFF00, #FF7E00, #FF0000, #8F3F97, #7E0023) + ý nghĩa và khuyến nghị sức khỏe (người bình thường / nhóm nhạy cảm) đúng văn bản.
- API mới `GET /api/v1/aqi/thang-do`: thang mức, màu, khuyến nghị, bảng ngưỡng.
- `frontend/aqi-vn.js`: nguồn duy nhất cho màu/mức/khuyến nghị ở mọi trang (thay cho các bảng màu tự định nghĩa ở từng trang). Trang Bản đồ có thẻ **Khuyến nghị sức khỏe** và chú thích thang màu 6 mức.
- Truy cập: liên kết "bỏ qua menu", vai trò ARIA cho menu, màu chữ đủ tương phản (chữ đen trên nền vàng/cam), chân trang ghi nguồn dữ liệu và căn cứ AQI, thẻ `meta description` cho mọi trang.
- Lưu ý: do sửa bảng ngưỡng, AQI lịch sử có PM10/O₃ chi phối sẽ thay đổi so với bản cũ; cảnh báo email dùng giá trị mới.

## v4.2 — Giao diện mới
- `frontend/style.css` viết lại thành hệ thống giao diện chung: font **Be Vietnam Pro** (Google Fonts, có dự phòng Segoe UI), banner đầu trang thống nhất, thẻ/bảng/nút/ô nhập cùng một kiểu, số liệu dùng chữ số cùng độ rộng.
- `frontend/nav.js`: logo "AirHCM" trên header, menu ☰ cho màn hình ≤ 760px, chân trang 3 cột (giới thiệu · chỉ số AQI · nguồn dữ liệu) luôn nằm đáy trang.
- Đã gỡ CSS riêng lặp lại ở từng trang (font, thẻ, tiêu đề, bảng) để mọi trang dùng chung. Muốn đổi màu/kiểu toàn web: sửa biến trong `:root` của `style.css`.
- Service worker lên `aqi-v4-2` (lưu cả font) để máy đã cài app nhận giao diện mới.

## v4.3 — Giao diện điện thoại và app Android
- Điện thoại (≤ 760px): thanh tab dưới đáy (Bản đồ · Dự báo · Cảnh báo · Thống kê · Thêm), menu "Thêm" trượt từ dưới lên, chừa vùng tai thỏ/thanh cử chỉ, ô chạm ≥ 44px; trang Bản đồ thu gọn chú thích để không che nút.
- App Android viết lại (`mobile/`, Capacitor 8): một APK dùng cho cả máy ảo lẫn điện thoại thật, tự dò máy chủ, đăng nhập hoạt động. Xem `mobile/README_MOBILE.md`.
- `chay_server_dien_thoai.bat`: chạy backend cho điện thoại cùng Wi-Fi truy cập.

## v4.4 — Trình bày kết quả và giới hạn theo chuẩn học thuật
- Trang mới `phuong-phap.html` (menu Hệ thống, chân trang): kết quả chính, kỹ năng theo tầm dự báo, bảng so sánh mô hình với mô hình nền, kiểm chéo cuốn chiếu kèm KTC 95%, quy trình, bảng "phạm vi dữ liệu → cách xử lý → hướng phát triển". Số liệu đọc trực tiếp từ API mới `GET /api/v1/danh-gia-mo-hinh` và `/api/v1/du-bao-gio/chi-so`.
- Ghi chú nguồn dữ liệu ở các trang: chuyển từ khung cảnh báo vàng sang dòng thông tin trung tính, có liên kết tới trang phương pháp; nội dung giới hạn giữ nguyên, diễn đạt lại theo văn phong khoa học.
- Trang Dự báo: dự báo theo giờ (đã có kỹ năng) đứng đầu; dự báo ngày mai đổi thành "xu hướng" kèm đánh giá thống kê.

## v4.5 — IoT mô phỏng (Wokwi ESP32 + MQTT)
- `iot/wokwi_tram/`: ESP32 + DHT22 + 2 biến trở (vai cảm biến bụi) + OLED + LED màu AQI, gửi JSON qua MQTT mỗi 5 giây. AQI tính ngay trên thiết bị bằng cùng bảng ngưỡng QĐ 1459 (có test so khớp với `ml/tinh_aqi.py`).
- `iot/wokwi_bang_dien_tu/`: ESP32 + LCD 20x4 + 6 LED màu mức AQI + còi, nhận bản tin AQI do hệ thống phát.
- `backend/services/iot.py`: nhận MQTT, lọc dữ liệu, lưu `du_lieu_iot` (cờ mô phỏng, bảng riêng), AQI trung bình 1 phút, sự kiện `iot.vuot_nguong` → thư cảnh báo (có trễ chống báo dồn dập), phát AQI cho bảng điện tử. API `/api/v1/iot/...`.
- Web: trang `iot.html` (thời gian thực, sơ đồ luồng, bản sao LCD, cảnh báo, nhật ký), lớp "IoT" trên Bản đồ, sơ đồ kiến trúc có thêm dải IoT.
- `iot/gia_lap/`: trạm và bảng điện tử ảo bằng Python (kiểm thử / dự phòng khi trình diễn). Hướng dẫn chi tiết: `iot/README.md`.

## v4.6 — Tự động lấy dữ liệu (không cần terminal)
- `data_pipeline/dong_bo_hang_ngay.py` viết lại: **tự lấy bù mọi ngày còn thiếu** (tính theo trạm thiếu lâu nhất, nên 1 trạm lỗi mạng sẽ được bù lần sau), làm mới 3 ngày gần nhất (dữ liệu thời tiết lưu trữ trễ vài ngày), khóa chống chạy chồng, ghi lịch sử vào bảng `lich_su_dong_bo` và nhật ký hệ thống.
- **Windows Task Scheduler** (`cai_dat_dong_bo_tu_dong.ps1`, chuột phải > Run with PowerShell): tác vụ `AQI_DongBoHangNgay` 7:30 hằng ngày, máy tắt thì chạy ngay khi bật lại, chạy nền bằng `pythonw` (không bật cửa sổ). Đã sửa lỗi cũ: tác vụ thiếu thư mục làm việc (0x8007010B) và `chay_dong_bo.bat` gọi sai đường dẫn sau khi sắp xếp lại thư mục.
- **Máy chủ** (`backend/services/dong_bo.py`): kiểm tra mỗi 10 phút, thiếu ngày hôm qua thì tự đồng bộ (tối đa 1 lần / 3 giờ); `DONG_BO_BAT`, `DONG_BO_GIO` trong `.env`.
- Trang **Trạng thái dữ liệu**: độ mới dữ liệu, lịch, lịch sử các lần đồng bộ; admin có nút **Đồng bộ ngay** và **Xem log**. API: `GET /api/v1/dong-bo/trang-thai`, `POST /api/v1/admin/dong-bo`, `GET /api/v1/admin/dong-bo/log`.

## v5.0 — Trang Tổng quan và công nghệ mới
- **Trang Tổng quan** (`tong-quan.html`, trang chủ `/`): đồng hồ AQI, so với ngưỡng WHO/QCVN và hôm qua, thời tiết hiện tại, PM2.5 dự báo 24 giờ có vạch ngưỡng, xu hướng 14 ngày, phân bố và xếp hạng trạm, trạm IoT trực tiếp. API gom một lần gọi: `GET /api/v1/tong-quan` (đệm 60 giây).
- **Thành phần dùng chung:** `AQI_VN.dongHo()` (đồng hồ AQI SVG, dùng ở Tổng quan, Cảnh báo, Bản đồ), `chart-theme.js` (giao diện chung cho mọi biểu đồ Chart.js + plugin nền dải màu AQI), khung chờ khi tải, thẻ hiện dần.
- **Server-Sent Events:** `GET /api/v1/su-kien` đẩy sự kiện công khai từ bus nội bộ tới trình duyệt (`iot.da_nhan`, `iot.vuot_nguong`, `du_lieu.da_nap`, `dong_bo.xong`); trang Trạm IoT, Tổng quan, Trạng thái dữ liệu cập nhật ngay, không hỏi lại định kỳ. `frontend/song-truc-tiep.js`.
- **Thông báo trình duyệt (Notification API):** nút "Báo cho tôi khi vượt ngưỡng" (Tổng quan, Trạm IoT); đã bật thì mọi trang đều nhận.
- **View Transitions API:** chuyển trang mượt, header và thanh tab đứng yên (Chromium; trình duyệt khác bỏ qua).
- **Trợ lý AirHCM** (nút "✨ Hỏi AI" trên header): trả lời câu hỏi dựa trên dữ liệu hiện tại; có `ANTHROPIC_API_KEY` thì dùng Claude (`claude-opus-5-5`, effort `low`, dự phòng khi bị từ chối `fallbacks: "default"`), không có thì trả lời tự động theo ý định câu hỏi. Giới hạn tần suất chống tốn phí. `POST /api/v1/tro-ly` (text/event-stream).
- Trang So sánh tự hiện sẵn so sánh trạm ô nhiễm nhất – trung tâm – sạch nhất; tiêu đề bảng không viết HOA nữa (tránh "µg/m³" thành "MG/M³").

## v5.1 — Chatbot Gemini trả lời về đồ án
- Trợ lý (nút "✨ Hỏi AI") hỗ trợ **Gemini** (`google-genai`): đặt `GEMINI_API_KEY` trong `.env` (lấy tại https://aistudio.google.com/apikey), model `GEMINI_MODEL` (mặc định `gemini-3.8-flash`). Chọn nhà cung cấp bằng `TRO_LY_NHA_CUNG_CAP` = `auto` (Gemini → Claude → tự động) | `gemini` | `claude`.
- Ngoài số liệu hiện tại, trợ lý được nạp **tài liệu dự án** (`README.md`, `iot/README.md`, `mobile/README_MOBILE.md`, tự đọc lại khi tệp đổi) nên trả lời được câu hỏi về kiến trúc, cách tính AQI, mô hình, IoT, cách chạy… Chỉ dùng thông tin có trong tài liệu, không bịa.
- Không có khóa: chế độ tự động có thêm ý định "đồ án" (tóm tắt kiến trúc, công nghệ, cách chạy).

## v6.0 — Bảo mật doanh nghiệp, chạy nền, triển khai 24/7, phân tích theo bài Lab
- **Phân tích theo bài Lab môn Python cho Máy học**: `ml/notebooks/Lab01_PM25_HCM.ipynb` (hồi quy, so sánh 6 mô hình, tương quan)
  và `Lab03_PM25_HCM.ipynb` (Prophet, tự hồi quy 7 ngày). Code giữ nguyên từ bài Lab, chỉ đổi dữ liệu đầu vào sang PM2.5 TP.HCM.
  `python ml/notebooks/xuat_bieu_do.py` chạy lại và đưa 12 biểu đồ lên trang Phương pháp. Kết quả trung thực:
  thời tiết cùng ngày giải thích khoảng 50% biến động PM2.5 (gió quan trọng nhất); tự hồi quy chỉ hơn "ngày mai = hôm nay" khoảng 6%.
- **Đăng nhập chuẩn doanh nghiệp**: xem mục Bảo mật; trang mới `tai-khoan.html`.
- **Chạy nền**: thông báo đẩy Web Push khi AQI vượt ngưỡng (trình duyệt, kể cả đã đóng trang); app Android tự kiểm tra AQI mỗi 30 phút
  (`@capacitor/background-runner`). Giao diện nền mới mượt trên điện thoại.
- **Triển khai 24/7 + SEO**: Docker đa kiến trúc (amd64/ARM64), Caddy HTTPS tự động, sao lưu hằng ngày, hướng dẫn Oracle Cloud miễn phí.
  Máy chủ tự chèn canonical, Open Graph, JSON-LD; có `robots.txt` và `sitemap.xml`.
- **Đóng gói đa nền tảng**: `cai_dat.ps1`/`cai_dat.sh`, `kiem_tra_moi_truong.py`; `requirements.txt` UTF-8 ghim đúng phiên bản khớp mô hình;
  `DATABASE_URL` dùng thống nhất; sửa build APK khi đường dẫn có dấu tiếng Việt.
- **Kiểm thử**: 136 ca tự động; `tools/kiem_thu_luong_du_lieu.py` kiểm 6 luồng dữ liệu đầu-cuối
  (nguồn ngoài → CSDL → đồng bộ → API → MQTT/SSE thời gian thực → CDC).

## v6.1 — Đăng nhập bằng Google, Facebook, Zalo
- Nút "Đăng nhập/Đăng ký bằng Google · Facebook · Zalo" ở `login.html` (chỉ hiện nhà cung cấp đã có khóa); liên kết/gỡ liên kết ở trang Tài khoản;
  tài khoản tạo bằng mạng xã hội có thể đặt mật khẩu sau. Trang `chinh-sach-rieng-tu.html` (Google/Facebook yêu cầu khi chạy chính thức).
- Kiểm thử: 138 ca tự động + 23 bước đầu-cuối với máy chủ nhà cung cấp giả lập (tạo tài khoản, gộp theo email xác minh, chặn state giả, bắt buộc 2 lớp, liên kết/gỡ).

## v6.2 — Đối chiếu với nghiên cứu đã công bố
- Bài báo đối chiếu: Rakholia và cs. (2022), *Urban Climate* 46, 101315, doi:10.1016/j.uclim.2022.101315 (dự báo PM2.5 theo giờ tại TP.HCM).
- `python ml/doi_chieu_bai_bao.py` bổ sung 3 phân tích bài báo có mà hệ thống chưa có, hiển thị ở trang Phương pháp (mục "Đối chiếu bài báo"):
  PM2.5 theo giờ trong ngày và ngày trong tuần; so sánh SGD – Gradient Boosting – MLP trên cùng tập kiểm tra; cửa sổ huấn luyện 3/6/12/24 tháng/toàn bộ.
- Kết quả: PM2.5 cao nhất lúc 22 giờ, thấp nhất lúc 11 giờ; Gradient Boosting và MLP ngang nhau (kỹ năng ≈ +30%), SGD +17%;
  dùng toàn bộ lịch sử tốt nhất (+31%), 3 tháng gần nhất chỉ +4% — khác quy trình "giai đoạn ngắn" của bài báo (dùng trạm đo mặt đất).
- Còn thiếu so với bài báo: số liệu trạm đo mặt đất thật; mô hình CNN-LSTM và XGBoost đúng như bài báo.

## v6.3 — Người dân gửi phản ánh ô nhiễm
- Trang `phan-anh.html`: chấm vị trí trên bản đồ (hoặc GPS), chọn loại (khói, đốt rác, bụi công trình, khí thải xe/nhà máy, mùi hôi, khác), mô tả.
  Ý tưởng theo Pham-Quoc và cs. (2021), doi:10.4108/eai.24-5-2021.169971 — bổ sung nguồn thông tin tại chỗ cho số liệu mô hình ~45 km.
- Phản ánh hiện ngay trên bản đồ (`phan-anh-layer.js`, cả trang Bản đồ) ở trạng thái "chưa xác minh" và chỉ gồm loại/vị trí/thời điểm;
  mô tả chỉ công khai sau khi admin xác minh. Người khác bấm "Tôi cũng thấy". Tự ẩn sau 72 giờ. Lưu kèm AQI thành phố lúc gửi.
- Chống lạm dụng: phải đăng nhập, 5 phản ánh/giờ/tài khoản, chỉ nhận vị trí trong vùng TP.HCM, không lộ tên/email người gửi.

## v6.4 — PostGIS dùng thật, đánh giá theo vùng, đánh giá kịch bản, tải ứng dụng
- **PostGIS** (lý do chọn và so sánh với SQL thường: `docs/CSDL_POSTGIS.md`): bảng `phuong_xa` 168 phường/xã sau sáp nhập 2025
  (`data_pipeline/nap_ranh_gioi.py`, tự nạp khi CSDL trống), chỉ mục GiST; truy vấn KNN trạm gần nhất, `ST_Contains`, `ST_Distance` mặt cầu.
- **Bản đồ nhiệt**: cắt theo ranh giới thành phố, xem theo phường, *Đánh giá theo vùng* (3 khu vực tỉnh cũ, 5 phường cao/thấp nhất,
  phân bố mức AQI), độ tin cậy theo khoảng cách tới trạm (≤ 5 / 5–15 / > 15 km); phần *Độ tin cậy* viết lại bằng lời dễ hiểu.
- **Kịch bản**: đánh giá kết quả (thay đổi %, mức AQI, ngưỡng QCVN/WHO, khuyến nghị), độ tin cậy (so với sai số mô hình,
  hai mô hình đồng thuận, khoảng dự báo 80%), bảng so sánh 6 kịch bản mẫu.
- **IoT trong CSDL**: tọa độ thiết bị dạng hình học PostGIS, tự gắn phường và trạm gần nhất; bảng `du_lieu_iot_gio` tổng hợp theo giờ giữ lâu dài.
- **Tải ứng dụng** (`tai-app.html`): APK Android, hướng dẫn cài lên iPhone dạng PWA, mã QR. 141 kiểm thử tự động.

## v6.5 — Tra cứu không gian: định vị, khoảng cách, vùng tròn/khung/đa giác, chỉ đường
- Trang `tra-cuu-khong-gian.html` (menu Phân tích): định vị GPS → cột mốc 📌 kéo được; quét **vòng tròn** (bán kính 0,2–20 km),
  **khung chữ nhật**, **đa giác** vẽ tay (Leaflet-Geoman, kéo đỉnh để chỉnh, kết quả tự cập nhật).
- PostGIS (`services/khong_gian.py`): `ST_DWithin` theo mét, `ST_Intersects`, tỉ lệ diện tích phường nằm trong vùng, khoảng cách tới cột mốc.
  **Xung đột hình học**: đa giác tự cắt bị chặn và đánh dấu điểm cắt (`ST_IsValidDetail`), có tùy chọn tự sửa (`ST_MakeValid`);
  chặn vùng ngoài TP.HCM, quá rộng, bán kính sai.
- Chỉ đường: OSRM (OpenStreetMap) vẽ tuyến theo đường phố + liên kết Google Maps; OSRM lỗi thì trả khoảng cách chim bay.
- Đã thử: trình duyệt máy tính, khổ điện thoại, **app trên máy ảo Android** (GPS máy ảo, chỉ đường). App: thêm quyền vị trí,
  tăng thời gian dò máy chủ 3 → 6 giây và tự thử lại 1 lần (lần mở đầu trên máy ảo trước đây báo không thấy máy chủ). 142 kiểm thử.

## Mã nguồn mở và bộ dữ liệu

- Mã nguồn: giấy phép **MIT** (tệp `LICENSE`). Tự do dùng, sửa, phân phối; giữ lại thông báo bản quyền.
- Bộ dữ liệu mở và giấy phép từng nguồn (CAMS, Open-Meteo, Sentinel-5P, ranh giới phường/xã): xem `du_lieu/README.md`.
- Mô hình đã huấn luyện ở `models/` (định dạng pickle/joblib). Chỉ nạp tệp mô hình từ nguồn bạn tin cậy.
- Chạy nhanh trên máy mới: `cai_dat.ps1` (Windows) hoặc `cai_dat.sh` (Linux/macOS), chạy máy chủ một lần để tạo bảng, rồi
  `python data_pipeline/du_lieu_mo.py --nhap` để nạp dữ liệu mẫu.
- Không có trong kho: `.env`, khóa Google, bản sao lưu CSDL, tệp APK. APK có ở mục Releases.
