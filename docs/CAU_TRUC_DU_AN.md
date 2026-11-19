# Cấu trúc mã nguồn — Hệ thống Giám sát & Dự báo Chất lượng Không khí TP.HCM (AirHCM)

Đồ án chuyên ngành · Lê Ngọc Ánh Dương (MSSV 1250080037) · GVHD: TS. Dương Thị Thúy Nga

Tài liệu này giải thích **vì sao mã nguồn được chia thành nhiều thư mục** và **mỗi thư mục, mỗi tệp đảm nhận chức năng gì**.

## 1. Nguyên tắc tổ chức

Hệ thống được tổ chức theo **kiến trúc nhiều lớp**. Mỗi thư mục cấp 1 là một thành phần độc lập, có đầu vào và đầu ra rõ ràng.
Nhờ vậy, mỗi phần có thể sửa, kiểm thử và triển khai riêng mà không ảnh hưởng đến phần khác.

```
 Nguồn dữ liệu                     Lưu trữ             Học máy               Máy chủ                Người dùng
 ──────────────                    ────────            ────────              ────────               ──────────
 Open-Meteo (CAMS)  ┐                                  ml/  ──huấn luyện──►  models/
 Sentinel-5P (GEE)  ├─► data_pipeline/ ─► PostgreSQL ──────────────────────► backend/ (FastAPI) ─┬─► frontend/ (web, PWA)
                    ┘   (tải, làm sạch,    + PostGIS        đọc mô hình ───►   API REST + SSE     ├─► mobile/   (app Android)
                                                       tests/ kiểm thử tự động các lớp trên
```

| Lớp | Thư mục | Vai trò |
|---|---|---|
| Thu thập dữ liệu | `data_pipeline/` | Tải dữ liệu vệ tinh và khí tượng, làm sạch, nạp vào cơ sở dữ liệu; đồng bộ tự động hằng ngày |
| Học máy | `ml/` | Tính VN_AQI; huấn luyện và dùng các mô hình dự báo, làm mịn không gian, phân cụm |
| Mô hình đã huấn luyện | `models/` | Kết quả đầu ra của `ml/`, được `backend/` nạp lên để dự báo |
| Máy chủ | `backend/` | API FastAPI: xác thực, dữ liệu, AQI, dự báo, cảnh báo, sự kiện thời gian thực, trợ lý AI |
| Giao diện web | `frontend/` | 22 trang web (bản đồ, dự báo, thống kê, báo cáo...), cài đặt được như ứng dụng (PWA) |
| Ứng dụng di động | `mobile/` | Đóng gói web thành ứng dụng Android (Capacitor) |
| Kiểm thử | `tests/`, `tools/` | 138 ca kiểm thử tự động (pytest) + kiểm thử đầu-cuối 6 luồng dữ liệu |
| Triển khai | `dong_goi/` | Docker đa kiến trúc, bản chạy 24/7 (Caddy HTTPS, sao lưu), kiểm tra môi trường, tạo bản nộp |
| Tài liệu | `docs/` | Tài liệu cấu trúc này, lịch sử phiên bản, hình minh họa |

## 2. Cây thư mục

```
air_quality_project/
├── backend/            Máy chủ API (FastAPI)
│   ├── main.py         Điểm khởi động: lắp ráp các router, phục vụ frontend/
│   ├── core/           Hạ tầng dùng chung: cấu hình, bảo mật đăng nhập, phiên, OAuth, SEO, email, nhật ký, bus sự kiện
│   ├── routers/        Các nhóm đường dẫn API (mỗi tệp = một nhóm chức năng)
│   └── services/       Xử lý nghiệp vụ, truy vấn PostGIS (router gọi service, service truy cập dữ liệu)
├── frontend/           Giao diện web: 22 trang HTML + mã JS/CSS dùng chung, PWA
├── ml/                 Tính AQI, huấn luyện, dự báo · notebooks/ (Lab01, Lab03 môn Python cho Máy học)
├── models/             Mô hình đã huấn luyện (.pkl, .joblib) + chỉ số đánh giá (.json)
├── data_pipeline/      Tải, làm sạch, nạp, đồng bộ dữ liệu; nạp ranh giới phường vào PostGIS
├── du_lieu/            gio_cache.csv (số liệu theo giờ đã tải) · ranh_gioi/ (168 phường/xã, bản gọn)
├── mobile/             Ứng dụng Android (Capacitor) + tệp cài đặt AirHCM.apk
├── tests/              142 kiểm thử tự động (pytest)
├── tools/              kiem_thu_luong_du_lieu.py: kiểm thử đầu-cuối 6 luồng dữ liệu trên máy chủ đang chạy
├── dong_goi/           Docker (máy cá nhân + máy chủ 24/7), Caddyfile, trien_khai/, kiểm tra môi trường, tạo bản nộp
├── docs/               Tài liệu: cấu trúc, CSDL PostGIS, triển khai Oracle, đăng nhập mạng xã hội
├── README.md           Giới thiệu, cách chạy, kết quả đánh giá, lịch sử phiên bản
├── requirements.txt    Thư viện Python (ghim phiên bản khớp mô hình) · requirements-dev.txt: thêm thư viện kiểm thử
├── .env.example        Mẫu cấu hình (cai_dat.ps1 / cai_dat.sh tự tạo .env với khóa ngẫu nhiên)
├── cai_dat.ps1, cai_dat.sh          Cài đặt 1 lệnh trên Windows / Linux, macOS
├── chay_server.bat, chay_server.sh  Chạy máy chủ
├── chay_server_dien_thoai.bat       Chạy máy chủ cho điện thoại cùng Wi-Fi truy cập
├── chay_dong_bo.bat                 Chạy đồng bộ dữ liệu bằng tay (chạy nền)
└── cai_dat_dong_bo_tu_dong.ps1      Cài lịch đồng bộ 7:30 hằng ngày vào Windows Task Scheduler
```

## 3. Chi tiết từng thành phần

### 3.1. `backend/` — Máy chủ API

| Tệp | Chức năng |
|---|---|
| `main.py` | Tạo ứng dụng FastAPI, gắn các router, phục vụ giao diện web; khi khởi động thì bật các dịch vụ nền (bus sự kiện, SSE, CDC, lịch đồng bộ, cảnh báo) |
| `database.py` | Kết nối PostgreSQL/PostGIS (SQLAlchemy) |
| `models.py` | Ánh xạ các bảng CSDL (ORM, có kiểu hình học PostGIS) |
| `schemas.py` | Định dạng dữ liệu vào/ra API (Pydantic), tự kiểm tra dữ liệu hợp lệ |
| `auth.py` | Băm mật khẩu Argon2id (tự nâng cấp hash bcrypt cũ), tạo và kiểm tra JWT có phân loại (phiên / mã tạm 2 lớp) |
| `seed_stations.py` | Nạp 10 trạm quan trắc mẫu |

**`core/` — hạ tầng dùng chung**

| Tệp | Chức năng |
|---|---|
| `config.py` | Nạp `.env`, đường dẫn dự án, CORS, cookie |
| `security.py` | Đọc JWT từ cookie HttpOnly, kiểm tra phiên phía máy chủ còn hiệu lực, kiểm tra quyền quản trị |
| `phien.py` | Phiên đăng nhập phía máy chủ (thu hồi được, hết hạn khi không hoạt động), xác thực 2 lớp TOTP + mã dự phòng, OTP đặt lại mật khẩu; tự tạo/nâng cấp bảng |
| `mat_khau.py` | Chính sách độ mạnh mật khẩu |
| `bao_mat_http.py` | Header bảo mật (CSP, chống iframe, HSTS), chống CSRF, cấm lưu cache dữ liệu cá nhân |
| `oauth.py` | Đăng nhập Google / Facebook / Zalo: OAuth 2.0 + PKCE, đọc hồ sơ từ nhà cung cấp |
| `seo.py` | Tự chèn canonical, Open Graph, JSON-LD vào trang HTML; sinh robots.txt, sitemap.xml |
| `ratelimit.py` | Khóa tạm đăng nhập: 5 lần sai/15 phút theo (email, IP), 20 lần theo email trên mọi IP; giới hạn tần suất chung |
| `mailer.py` | Gửi email qua SMTP |
| `logbus.py` | Nhật ký tập trung: mọi thành phần ghi về một bảng `nhat_ky_he_thong` |
| `events.py` | Bus sự kiện nội bộ theo mô hình publish/subscribe |
| `day_su_kien.py` | Đẩy sự kiện từ bus ra trình duyệt bằng Server-Sent Events (SSE) |

**`routers/` — các nhóm API** (mỗi tệp tương ứng một nhóm chức năng trên web)

| Tệp | API cho chức năng |
|---|---|
| `auth.py` | Đăng ký, đăng nhập, xác thực 2 lớp, đăng xuất, quản lý thiết bị, đổi mật khẩu, quên mật khẩu (OTP qua email) |
| `oauth.py` | Bắt đầu/nhận kết quả đăng nhập mạng xã hội, tạo hoặc gộp tài khoản, liên kết/gỡ liên kết |
| `khong_gian.py` | Quét vùng tròn/khung/đa giác (PostGIS), trạm gần nhất (KNN), chỉ đường OSRM + Google Maps |
| `ranh_gioi.py` | Ranh giới 168 phường/xã từ PostGIS (GeoJSON, đường bao thành phố, tra cứu tọa độ → phường) |
| `ung_dung.py` | Tải tệp APK Android, thông tin + mã QR cho trang tai-app.html |
| `phan_anh.py` | Phản ánh ô nhiễm của người dân: gửi, xem trên bản đồ, "Tôi cũng thấy", duyệt (admin) |
| `day.py` | Thông báo đẩy Web Push (đăng ký, gửi thử); AQI gọn cho tác vụ nền của app |
| `seo.py` | `/robots.txt`, `/sitemap.xml` |
| `tram.py` | Quản lý trạm quan trắc (thêm/sửa/xóa) |
| `du_lieu.py` | Dữ liệu quan trắc: heatmap, theo giờ, theo trạm |
| `aqi.py` | AQI theo trạm, toàn bộ trạm, theo ngày |
| `tong_quan.py` | Trang Tổng quan (gom AQI, thời tiết, dự báo 24 giờ, xếp hạng điểm ước tính) |
| `du_bao.py`, `du_bao_gio.py` | Dự báo PM2.5 theo ngày và theo giờ (24 giờ tới) |
| `ban_do_nhiet.py` | Bản đồ nhiệt dự báo (dự báo theo trạm rồi nội suy không gian) |
| `kich_ban.py` | Kịch bản "nếu đầu vào thay đổi thì PM2.5 thay đổi thế nào" |
| `dong_thoi_gian.py` | Thanh thời gian trên bản đồ |
| `thong_ke.py`, `bao_cao.py` | Thống kê; xuất báo cáo Excel/PDF |
| `canh_bao.py`, `luong_canh_bao.py` | Đăng ký cảnh báo email; trình diễn luồng cảnh báo từng bước (admin) |
| `su_kien.py` | Luồng sự kiện thời gian thực (SSE) |
| `tro_ly.py` | Trợ lý AI (Gemini), trả lời theo luồng |
| `dong_bo.py`, `admin_gee.py` | Trạng thái và chạy đồng bộ dữ liệu; chạy xử lý GEE (admin) |
| `nhat_ky.py`, `he_thong.py` | Tra cứu nhật ký (admin); kiểm tra tình trạng hệ thống (health check) |

**`services/` — xử lý nghiệp vụ**

| Tệp | Chức năng |
|---|---|
| `aqi.py` | Tính AQI dùng chung cho các router (gọi `ml/tinh_aqi.py`) |
| `openmeteo.py` | Lấy số liệu theo giờ từ Open-Meteo, có bộ nhớ đệm 30 phút |
| `tong_quan.py` | Tổng hợp số liệu trang Tổng quan, đệm 60 giây |
| `du_bao_gio.py` | Dự báo PM2.5 1–24 giờ tới |
| `ban_do_nhiet.py` | Nội suy IDW và đánh giá độ tin cậy bằng phương pháp "bỏ một trạm" |
| `kich_ban.py` | Mô phỏng kịch bản bằng mô hình ước lượng trong ngày |
| `dong_thoi_gian.py` | Dữ liệu cho thanh thời gian (theo ngày từ CSDL, theo giờ từ Open-Meteo) |
| `canh_bao_service.py` | Quét ngưỡng AQI và gửi email (tối đa 1 thư/ngày/đăng ký) |
| `cdc.py` | Bắt thay đổi dữ liệu bằng PostgreSQL LISTEN/NOTIFY (CDC) rồi phát lên bus sự kiện |
| `dong_bo.py` | Lịch đồng bộ chạy trong máy chủ (bổ sung cho lịch Windows) |
| `tro_ly.py` | Trợ lý AI: ghép dữ liệu thật + tài liệu dự án, gọi Gemini (tự chuyển sang mô hình dự phòng khi lỗi) |
| `day_thong_bao.py` | Web Push: khóa VAPID, quét AQI mỗi 30 phút, gửi thông báo nền khi vượt ngưỡng |

### 3.2. `frontend/` — Giao diện web

| Trang | Chức năng |
|---|---|
| `tong-quan.html` | Tổng quan: AQI hiện tại, thời tiết, dự báo 24 giờ, xếp hạng trạm |
| `index.html` | Bản đồ AQI (Leaflet), thanh thời gian |
| `ban-do-nhiet.html` | Bản đồ nhiệt dự báo PM2.5 |
| `du-bao.html`, `kich-ban.html` | Dự báo theo ngày/giờ; thử kịch bản thay đổi đầu vào |
| `tram.html`, `so-sanh.html` | Quản lý trạm; so sánh các trạm |
| `thong-ke.html`, `bao-cao.html` | Thống kê; xuất báo cáo |
| `canh-bao.html` | Đăng ký nhận cảnh báo email |
| `tra-cuu-khong-gian.html` | Định vị GPS, quét vùng tròn/khung/đa giác kéo thả được, khoảng cách, chỉ đường |
| `tai-app.html` | Tải ứng dụng: APK cho Android, hướng dẫn cài lên iPhone (PWA), mã QR |
| `phan-anh.html` | Người dân gửi phản ánh ô nhiễm (khói, đốt rác, bụi công trình...) lên bản đồ; admin duyệt |
| `trang-thai-du-lieu.html` | Tình trạng cập nhật dữ liệu và lịch sử đồng bộ |
| `nhat-ky.html`, `luong-canh-bao.html` | Nhật ký hệ thống; trình diễn luồng cảnh báo (admin) |
| `gioi-thieu.html`, `phuong-phap.html` | Giới thiệu đề tài; phương pháp và kết quả kiểm chứng |
| `login.html` | Đăng nhập (kèm bước xác thực 2 lớp) / đăng ký / quên mật khẩu |
| `tai-khoan.html` | Tài khoản & bảo mật: đổi/đặt mật khẩu, bật 2 lớp, liên kết Google/Facebook/Zalo, thiết bị đang đăng nhập, thông báo nền |
| `chinh-sach-rieng-tu.html` | Chính sách quyền riêng tư + hướng dẫn xóa dữ liệu |

| Tệp dùng chung | Chức năng |
|---|---|
| `nav.js`, `style.css` | Menu và giao diện chung của mọi trang |
| `aqi-vn.js`, `chart-theme.js` | Thang màu VN_AQI; giao diện biểu đồ Chart.js |
| `app-config.js` | Địa chỉ máy chủ API (dùng chung cho web, PWA, app) |
| `song-truc-tiep.js` | Nhận sự kiện thời gian thực (SSE) và hiện thông báo |
| `tro-ly.js` | Khung chat trợ lý AI dạng bong bóng nổi |
| `thong-bao-day.js` | Bật/tắt thông báo cảnh báo chạy nền (Web Push) |
| `hinh/ml/` | 12 biểu đồ + chỉ số xuất từ notebook phân tích (trang Phương pháp) |
| `phan-anh-layer.js` | Lớp phản ánh của người dân trên bản đồ |
| `sw.js`, `pwa.js`, `manifest.webmanifest`, `icons/` | Progressive Web App: cài lên máy, dùng khi mất mạng |
| `kien_truc_hien_tai.svg`, `kien_truc_mo_rong.svg` | Sơ đồ kiến trúc hiện tại và hướng mở rộng |

### 3.3. `ml/` — Học máy

| Tệp | Chức năng |
|---|---|
| `tinh_aqi.py` | Tính VN_AQI theo QĐ 1459/QĐ-TCMT |
| `train_model.py` | Huấn luyện mô hình PM2.5 theo ngày (Random Forest, so với mô hình nền), ghi lịch sử bằng MLflow |
| `train_du_bao_gio.py` | Huấn luyện mô hình dự báo theo giờ, đánh giá theo thứ tự thời gian |
| `train_diem.py` | Huấn luyện mô hình theo từng trạm (cho bản đồ nhiệt) |
| `train_downscale_model.py` | Làm mịn không gian (spatial downscaling) PM2.5, PM10, O₃ |
| `phan_cum_tram.py` | Phân cụm các trạm theo mức ô nhiễm (K-Means) |
| `predict.py` | Dùng mô hình đã huấn luyện để dự báo theo ngày |
| `notebooks/Lab01_PM25_HCM.ipynb` | Code bài Lab01 môn Python cho Máy học (hồi quy, 6 mô hình, tương quan) áp dụng cho PM2.5 TP.HCM |
| `notebooks/Lab03_PM25_HCM.ipynb` | Code bài Lab03 (Prophet, tự hồi quy 7 ngày) áp dụng cho PM2.5 TP.HCM, so với mô hình nền |
| `notebooks/xuat_bieu_do.py` | Chạy 2 notebook và xuất biểu đồ lên web |
| `doi_chieu_bai_bao.py` | Đối chiếu với bài báo Rakholia và cs. (Urban Climate 2022): đặc điểm PM2.5 theo giờ/ngày trong tuần, so sánh SGD – Gradient Boosting – MLP, thí nghiệm cửa sổ huấn luyện |

`models/` chứa kết quả của các script trên: `random_forest_pm25*.pkl`, `downscale_*.pkl`, `du_bao_gio.joblib`, `kmeans_phan_cum.pkl`... cùng các tệp `.json` lưu chỉ số đánh giá được hiển thị trên trang Phương pháp.

### 3.4. `data_pipeline/` — Thu thập dữ liệu

| Tệp | Chức năng |
|---|---|
| `stations_config.py` | Nguồn duy nhất cho danh sách trạm (đọc từ CSDL, không viết cứng) |
| `download_openmeteo_data.py` | Tải PM2.5, PM10, O₃, thời tiết từ Open-Meteo theo từng trạm |
| `download_gee_data.py`, `gee_extract.py` | Tải NO₂, CO, SO₂ từ vệ tinh Sentinel-5P qua Google Earth Engine |
| `run_pipeline.py` | Quy trình tổng: tải → làm sạch → nạp CSDL |
| `run_batch_years.py`, `run_batch_stations.py` | Chạy theo lô từng tháng/từng trạm (tránh giới hạn 5000 phần tử của GEE) |
| `load_to_db.py` | Nạp CSV vào PostgreSQL/PostGIS |
| `nap_ranh_gioi.py` | Nạp ranh giới 168 phường/xã (bản gọn `du_lieu/ranh_gioi/phuong_xa_hcm.geojson`) vào PostGIS, tạo chỉ mục GiST |
| `db_url.py` | Chuỗi kết nối CSDL dùng chung (ưu tiên DATABASE_URL) |
| `dong_bo_hang_ngay.py` | Đồng bộ tự động hằng ngày, tự lấy bù ngày thiếu, có khóa chống chạy chồng |
| `kiem_tra_du_lieu.py` | Kiểm tra chất lượng dữ liệu (chỉ đọc) |
| `tai_tram_that.py`, `doi_chieu_tram_that.py` | Tải số đo thực tế từ OpenAQ (kèm QA/QC loại mã lỗi ≥ 900) và đối chiếu sai số với mô hình CAMS |
| `du_lieu_mo.py` | Xuất/nhập bộ dữ liệu mở (`du_lieu/mo/*.csv`) |
| `them_khoa_ngoai.py` | Thêm khóa ngoại để sơ đồ ERD hiển thị quan hệ giữa các bảng |

### 3.6. `mobile/` — Ứng dụng Android

| Tệp | Chức năng |
|---|---|
| `AirHCM.apk` | Tệp cài đặt ứng dụng Android |
| `www/index.html`, `www/loi.html` | Màn hình khởi động (tìm máy chủ: Internet → máy ảo → Wi-Fi) và màn hình mất kết nối |
| `www/runners/kiem_tra_aqi.js` | Tác vụ nền: kiểm tra AQI mỗi 30 phút, báo bằng thông báo Android kể cả khi đóng app |
| `capacitor.config.json`, `android/` | Cấu hình và dự án Android do Capacitor tạo |
| `build_apk.js`, `chay_may_ao.js` | Build APK; mở máy ảo và cài app |
| `package.json`, `package-lock.json` | Khai báo thư viện Node.js (cài bằng `npm install`) |

### 3.7. `tests/` — Kiểm thử tự động

148 ca kiểm thử chạy **không cần CSDL và không gọi API thật**: tính AQI (`test_aqi.py`), xác thực (`test_auth.py`), dự báo theo ngày/giờ (`test_train_model.py`, `test_predict.py`, `test_du_bao_gio.py`), bản đồ nhiệt (`test_ban_do_nhiet.py`), kịch bản (`test_kich_ban.py`), đồng bộ (`test_dong_bo.py`), IoT (`test_iot.py`), trợ lý AI (`test_tro_ly.py`), đối chiếu trạm thật (`test_doi_chieu.py`), bảo mật đăng nhập + SEO (`test_bao_mat.py`).

Kiểm thử đầu-cuối trên máy chủ đang chạy (dùng CSDL và mạng thật): `python tools/kiem_thu_luong_du_lieu.py`.

```
cd backend
python -m pytest ../tests -q
```

## 4. Những gì không có trong bản nộp và lý do

| Không nộp | Lý do | Tạo lại bằng |
|---|---|---|
| `venv/` | Thư viện Python tải về (~35.000 tệp) | `python -m venv venv` rồi `pip install -r requirements.txt` |
| `mobile/node_modules/` | Thư viện Node.js tải về (83 gói) | `cd mobile` rồi `npm install` |
| `build/`, `.gradle/` | Tệp biên dịch Android | `npm run apk` |
| `.env`, `gee-key.json`, `bi_mat/` | **Khóa bí mật** (CSDL, JWT, email, Gemini, Google, VAPID) | Chạy `cai_dat.ps1`/`cai_dat.sh` hoặc sao chép `.env.example` thành `.env`; khóa VAPID tự sinh |
| `backup.sql` | Bản sao CSDL, có dữ liệu tài khoản người dùng | Cung cấp riêng khi cần |
| `mlruns/`, `mlflow.db` | Lịch sử các lần huấn luyện (MLflow) | Tự sinh khi chạy `ml/train_model.py` (nếu cài mlflow) |
| `log_dong_bo.txt`, `__pycache__/` | Nhật ký và bộ nhớ đệm của máy | Tự sinh khi chạy |

Bản nộp được tạo bằng `python dong_goi/tao_ban_nop.py`. Script tự loại các mục trên, rồi **quét mọi tệp sẽ nộp** để chắc chắn không có khóa API hay mật khẩu nào lọt vào trước khi nén.

## 5. Cách chạy

| Cách | Lệnh |
|---|---|
| Windows | Chuột phải `cai_dat.ps1` → *Run with PowerShell*, rồi bấm đúp `chay_server.bat` |
| Linux / macOS | `bash cai_dat.sh` rồi `bash chay_server.sh` |
| Docker (mọi hệ điều hành, x86-64/ARM64) | `docker compose -f dong_goi/docker-compose.yml up -d --build` |
| Máy chủ Internet 24/7 | `docs/TRIEN_KHAI_ORACLE.md` |

Mở `http://localhost:8000` (tài liệu API ở `/docs` khi `MOI_TRUONG=development`). Kiểm tra môi trường: `python dong_goi/kiem_tra_moi_truong.py`.
