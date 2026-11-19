# Prompt bàn giao: toàn bộ quá trình làm AirHCM (đọc trước khi làm tiếp)

> Dán toàn bộ tệp này vào phiên trợ lý AI mới (mở trong thư mục dự án), hoặc bảo trợ lý: "Đọc docs/BAN_GIAO_PHIEN_CHAT.md".
> Cập nhật đến 18/11/2026 (v6.8).

---

Bạn là trợ lý lập trình tiếp tục đồ án **AirHCM — Hệ thống giám sát, quản lý và dự báo chất lượng không khí TP.HCM**.
Đọc hết tệp này trước khi làm. Mọi số liệu dưới đây đã được kiểm chứng ở phiên trước; nếu cần dùng lại, hãy kiểm tra lại trên máy.
P
## 1. Người dùng và cách làm việc
- Sinh viên **Lê Ngọc Ánh Dương** (MSSV 1250080037), lớp 12_ĐH_THMT; GVHD **TS. Dương Thị Thúy Nga**. Đồ án chuyên ngành, sắp bảo vệ.
- Người dùng nhắn tiếng Việt **không dấu**, thường viết hoa; **luôn trả lời tiếng Việt có dấu, ngắn gọn, thẳng vào việc**.
- Người dùng không chuyên kỹ thuật sâu: hướng dẫn thao tác web (Google Cloud, Cloudflare, nhà đăng ký tên miền) theo **từng bước, ghi rõ tên nút**.
- Người dùng muốn đánh giá **thẳng thắn kiểu hội đồng khó tính** (họ đã hỏi "vai trò hội đồng Bách khoa"); không tô hồng.
- Làm xong phần nào: chạy kiểm thử, commit, `git push` (kho đã công khai, người dùng đồng ý đẩy lên thường xuyên).

## 2. Đường dẫn, môi trường, bẫy đã gặp
- Dự án: `E:\duongadmin\OneDrive\Máy tính\projectcn\air_quality_project` (có dấu "Máy tính", nằm trong OneDrive). Git, nhánh `main`,
  remote `https://ElrynSol@github.com/ElrynSol/AirHCMcity.git` (máy còn lưu đăng nhập tài khoản khác "SaberWaifu" — phải có `ElrynSol@` trong URL).
- Windows 11, Python venv `venv\`, PostgreSQL 17 + PostGIS 3.6 (`C:\Program Files\PostgreSQL\17\bin`), Node.js, Android SDK (máy ảo `Medium_Phone`), JDK 17/23.
- Chạy Python luôn kèm `-X utf8` (không thì `print` tiếng Việt làm uvicorn chết, lỗi cp1258). Máy chủ thử: cổng **8001**; cổng 8000 để người dùng tự chạy.
- Đường dẫn Unicode: Prophet cần `tbb.dll` chép cạnh `prophet_model.bin`; Gradle cần `subst` (mobile/build_apk.js đã xử lý); Kotlin ép jvmTarget 21.
- Heredoc bash: `\b`, `\n` trong chuỗi Python bị hiểu thành ký tự điều khiển — sửa tệp có dấu `\` bằng công cụ Edit hoặc `chr(92)`.
- Edge headless `--screenshot/--dump-dom` đóng băng hiệu ứng và có thể kẹt với SSE → kiểm tra giao diện thật bằng DevTools (CDP): script mẫu
  ở thư mục scratchpad phiên trước (`cdp_kiem.py`: mở Edge `--remote-debugging-port`, chờ, `Runtime.evaluate`, `Page.captureScreenshot`).
- **Bảo mật bắt buộc:** không in giá trị trong `.env` (xem thì che: `sed 's/=.*/=***/'`); không commit `.env`, khóa, bản sao lưu.
  Khóa Google `gee-key.json` và bản sao lưu nằm ở `C:\Users\duong\.airhcm\` (ngoài OneDrive), `.env` trỏ bằng `GEE_KEY_FILE`.
  `.env` có: DB, JWT, SMTP, GEMINI, GOOGLE_CLIENT_ID/SECRET, OPENAQ_API_KEY, TEN_MIEN=airhcmcity.asia. Khóa OpenAQ từng lộ trong nhật ký công cụ → nên tạo khóa mới.
- Tắt tiến trình (Stop-Process) bị bộ phân loại an toàn chặn → nhờ người dùng tắt qua Task Manager.

## 3. Kiến trúc hiện tại (v6.8)
- **Backend** FastAPI (`backend/`): routers + services; PostgreSQL/PostGIS (bảng `phuong_xa` 168 phường, GiST, KNN, ST_DWithin…);
  đăng nhập Argon2id + phiên phía máy chủ + 2FA TOTP + chống CSRF + OAuth Google/Facebook/Zalo (PKCE); Web Push; SSE; chatbot Gemini/Claude.
- **Frontend** `frontend/` 24 trang HTML + `nav.js` (menu một chỗ), `aqi-vn.js` (thang VN_AQI + `qcvnPM25()`), `sw.js` (PWA, tăng `PHIEN_BAN` khi đổi giao diện).
- **ML** `ml/`: dự báo theo giờ HistGradientBoosting (`train_du_bao_gio.py`), theo ngày Random Forest (`predict.py`, 7 ngày tính từ **ngày hệ thống**,
  bù khoảng trống ≤ 7 ngày), xu hướng tháng (khí hậu học), `mo_hinh_tram_that.py` (học từ số đo thật), `du_bao_da_chat.py` (PM2.5/PM10/O₃),
  `danh_gia_xac_suat.py` (PICP, Brier). Kết quả ở `models/*.json` (giải thích: `models/README.md`).
- **Dữ liệu**: CAMS qua Open-Meteo (mô hình, lưới ~45 km), Sentinel-5P (cột khí), gió ERA5, số đo thật OpenAQ (`data_pipeline/tai_tram_that.py`).
  Bộ dữ liệu mở `du_lieu/mo/*.csv` (`data_pipeline/du_lieu_mo.py --xuat/--nhap`).
- **App Android** Capacitor (`mobile/`, `npm run apk`, tự thử `https://airhcmcity.asia` trước).
- **Triển khai**: tên miền `airhcmcity.asia` (PA Vietnam, hết hạn 17/11/2027) → Cloudflare (nameserver kirk/magali) → **Cloudflare Tunnel** tên `airhcm`
  (`~/.cloudflared/config.yml` → `http://127.0.0.1:8000`) → máy chủ trên laptop. Bật bằng `chay_cong_khai.bat`. Chỉ chạy khi laptop bật.
  Google Search Console đã xác minh (TXT), đã gửi sitemap. Bộ Docker + script cho máy chủ 24/7 có sẵn (`dong_goi/`) nhưng chưa thuê được
  (Oracle từ chối đăng ký; Google Cloud đòi trả trước 800.000 ₫ — người dùng không chi được).

## 4. Dòng thời gian đã làm (tóm tắt)
- **v4–v5** (trước 11/2026): VN_AQI theo QĐ 1459, giao diện, app Android, trang Tổng quan, chatbot.
- **v6.0** (12/11): bảo mật doanh nghiệp, Web Push, Docker đa kiến trúc, SEO, notebook theo bài Lab môn Python cho Máy học.
- **v6.1–6.2**: đăng nhập Google/Facebook/Zalo (Google chạy thật); đối chiếu bài báo Rakholia và cs. 2022.
- **v6.3–6.5** (16–17/11): phản ánh của người dân; PostGIS dùng thật; tra cứu không gian (GPS, vùng tròn/khung/đa giác, xung đột hình học, OSRM).
- **17/11**: đưa lên GitHub (MIT, kèm dữ liệu, mô hình); mua tên miền, Cloudflare Tunnel, Search Console; APK trỏ tên miền.
- **v6.6** (17–18/11): làm lại 6 trang cho người không chuyên (Kịch bản, Bản đồ nhiệt, Dự báo, Thống kê, So sánh, Tổng quan).
- **v6.7** (18/11, theo PDF đề cương "Dự báo, phân tích xác suất và truy tìm nguồn thải" của Lê Hoàng Ân): ngưỡng QCVN PM2.5 24h **45 từ 01/01/2026**
  (`backend/core/nguong.py`), trang **Hoa gió ô nhiễm** (`hoa-gio.html`, ERA5, F_k/P_k/CBPF, thang bằng chứng A–E), 7 ngày theo ngày hệ thống,
  xác suất vượt ngưỡng, xu hướng tháng, bảng biện pháp theo nguồn.
- **18/11**: lấy số đo thật OpenAQ (Lãnh sự quán Mỹ — QA/QC loại mã lỗi 985; AirGradient CMT8; Linh Trung), trang Phương pháp có mục đối chiếu.
- **v6.8** (18/11, sau đánh giá "hội đồng"): **gỡ IoT** (MQTT công khai, khóa lộ); đổi "trạm quan trắc" → **"điểm ước tính"** + khung ghi rõ số liệu mô hình;
  mô hình **học từ số đo thật**; dự báo PM10/O₃; khảo sát **SUS** (`khao-sat.html`); bảng so sánh hệ thống hiện có; kiểm thử giao diện tĩnh;
  bỏ gọi cứng `localhost:8000`; `sao_luu_csdl.ps1`; README có bảng "muốn làm gì thì bấm tệp nào".

## 5. Kết quả chính (dùng cho báo cáo — đừng tô hồng)
- **CAMS so với trạm thật** (theo ngày): CMT8 672 ngày — CAMS thấp hơn 2,9 µg/m³ (≈ 9%), MAE 10,6, r = 0,29, bỏ sót 59/77 ngày vượt QCVN;
  Lãnh sự quán 167 ngày — lệch −4,3, r = 0,16.
- **Dự báo PM2.5 THẬT ngày mai tại CMT8** (194 ngày kiểm tra, mùa mưa 05–11/2026): "mai = hôm nay" MAE 6,1; **CAMS thô kém hơn 78%**
  (KTC −133…−30%); CAMS cộng bù lệch kém hơn 116%; Ridge / Random Forest hơn ≈ 5% (KTC chứa 0 → chưa chứng minh).
- **Dự báo theo chất (so với CAMS)**: Ridge hơn "mai = hôm nay" PM2.5 +7% (KTC 4…10%), PM10 +5%, O₃ +6% — có ý nghĩa thống kê.
- **Xác suất (32 ngày ngoài mẫu)**: PICP khoảng 80% = 81%; kỹ năng +11%; Brier vượt WHO 0,062 vs 0,059 khí hậu (BSS −0,06) → ghi "thử nghiệm".
- **Xu hướng tháng**: backtest 50 tháng MAE 3,2 vs 4,4 ("tháng sau = tháng trước"), kỹ năng +28%.
- **Hoa gió 3 tháng**: gió nhiều nhất Tây Nam (21%); gió Tây Bắc kéo bụi cao nhất (65% số giờ > 25 µg/m³); lặng gió 4%.
- 201 kiểm thử (`cd backend; python -m pytest ../tests -q`).

## 6. Đánh giá "hội đồng" gần nhất (đã nói với người dùng)
Độ tin cậy: số liệu ≈ 40%, bản đồ phường ≈ 25%, dự báo ≈ 45%, minh bạch ≈ 85%, kỹ thuật ≈ 75%, vận hành ≈ 45%, đánh giá người dùng ≈ 5% (0 phiếu SUS).
Tổng thể ≈ 60–65% nếu định vị là "giám sát xu hướng dựa trên mô hình, có kiểm chứng". Rủi ro lớn nhất: sinh viên không giải thích được hệ thống
(lịch sử git chỉ từ 17/11). Dự kiến 7–8 điểm nếu trả lời tốt.

## 7. Việc còn lại
**Người dùng phải làm:** tắt máy chủ cũ đang giữ cổng 8000 (PID có lệnh `uvicorn ... --port 8000` không có `--reload`, chạy mã cũ còn IoT) rồi
bật `chay_cong_khai.bat`; chạy `cai_dat_dong_bo_tu_dong.ps1` (lịch đồng bộ cũ trỏ sai thư mục); lấy 15–20 phiếu SUS; Publish OAuth Google;
cài APK lên điện thoại thật; đối chiếu QCVN 05:2023 gốc (mốc 45 và định nghĩa µg/Nm³ chưa xác minh được); tạo lại khóa OpenAQ.
**Nộp cô (theo mail):** mã nguồn + CSDL + CSV (có), link phần mềm (có), APK (có), **video hướng dẫn cài đặt + video hướng dẫn sử dụng** (chưa),
**Word báo cáo tổng kết** (chưa — bản đợt 2 cũ ở thư mục cha), **PPT** (chưa).
**Đề xuất tiếp theo:** (1) bộ 30 câu hỏi hội đồng kèm đáp án; (2) Word báo cáo lấy "CAMS kém số đo thật" làm kết quả chính; (3) PPT; (4) kịch bản 2 video;
(5) tạo zip nộp: `python dong_goi/tao_ban_nop.py --kiem-thu`.

## 8. Nguyên tắc khi làm tiếp
- Không gọi T01–T17 là "trạm quan trắc"; gọi "điểm ước tính". Mọi kết luận độ chính xác phải phân biệt "so với CAMS" và "so với số đo thật".
- Không thêm tính năng mới nếu chưa được yêu cầu — đề tài đã bị xem là dàn trải; ưu tiên chiều sâu, kiểm chứng, tài liệu.
- Sau khi sửa giao diện: tăng `PHIEN_BAN` trong `frontend/sw.js`, chạy kiểm thử (gồm `tests/test_giao_dien.py`), kiểm tra bằng CDP trên cổng 8001.
