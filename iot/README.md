# IoT mô phỏng (Wokwi ESP32 + MQTT)

Ba hướng đã làm:
1. **Trạm cảm biến** (`wokwi_tram/`) gửi số đo lên hệ thống.
2. **Luồng cảnh báo tức thời**: vượt ngưỡng → sự kiện → thư cảnh báo → bảng điện tử phản ứng ngay.
3. **Bảng điện tử** (`wokwi_bang_dien_tu/`) nhận AQI do hệ thống phát.

```
Trạm ESP32 ──MQTT──► broker.hivemq.com ──► backend/services/iot.py ──► du_lieu_iot (CSDL, cờ mô phỏng)
 DHT22, 2 biến trở PM,                         │ AQI TB 1 phút (QĐ 1459)
 OLED, LED màu AQI                             ├─► sự kiện iot.vuot_nguong ─► thư cảnh báo (Hộp thư đã gửi / email)
                                               └─► phát AQI (retained) ─────► Bảng điện tử ESP32: LCD 20x4, 6 LED, còi
```

> **Dữ liệu mô phỏng.** Lưu ở bảng riêng `du_lieu_iot`, gắn cờ `mo_phong`, không trộn vào `du_lieu_tram_mat_dat` và không dùng huấn luyện mô hình. Trên web luôn có nhãn "MÔ PHỎNG".

## Chạy bằng Wokwi trong VS Code
Extension Wokwi trong VS Code **không tự biên dịch** code Arduino. Nó chạy firmware đã biên dịch sẵn, được khai báo trong `wokwi.toml` của từng project.
1. Biên dịch (lần đầu sẽ tự cài bộ biên dịch ESP32 và các thư viện, mất vài phút): chạy `iot\build_firmware.bat`.
   Kết quả nằm ở `iot/<project>/build/` (đã có trong `.gitignore`). **Sửa file `.ino` thì phải chạy lại.**
2. Lần đầu dùng extension: F1 → **Wokwi: Request a New License** (miễn phí, đăng nhập tài khoản Wokwi trên trình duyệt).
3. Mở `iot/wokwi_tram/diagram.json` trong VS Code → F1 → **Wokwi: Start Simulator**. Wi-Fi `Wokwi-GUEST` ra Internet qua cổng chung của Wokwi, nên kết nối được broker MQTT công cộng.
4. Bảng điện tử: mở **cửa sổ VS Code thứ hai** (File → New Window) tại thư mục `iot/wokwi_bang_dien_tu/` rồi làm tương tự. Mỗi cửa sổ chỉ chạy được một mô phỏng.

## Chạy trên Wokwi (trình duyệt)
1. Chạy backend như bình thường. Trạng thái MQTT xem ở trang **Trạm IoT** (`/iot.html`) hoặc `GET /api/v1/iot/trang-thai`.
2. Mở https://wokwi.com/projects/new/esp32 rồi:
   - dán nội dung `wokwi_tram/wokwi_tram.ino` vào tab **sketch.ino**, dán `wokwi_tram/diagram.json` vào tab **diagram.json**;
   - tab **Library Manager** → nút **+** → thêm lần lượt các thư viện trong `wokwi_tram/libraries.txt`;
   - bấm ▶. Màn OLED hiện "WiFi OK MQTT OK", Serial Monitor in các gói JSON.
3. Mở **tab trình duyệt thứ hai** và làm tương tự với `wokwi_bang_dien_tu/`.
4. Muốn giữ project: đăng nhập Wokwi → **Save** → **Share** để có đường link mở lại nhanh khi trình diễn.

## Kịch bản trình diễn (khoảng 1 phút)
1. Mở trang **Bản đồ**: ô vuông "IoT" ở Quận 3 nhấp nháy, nghĩa là trạm đang gửi dữ liệu.
2. Mở trang **Trạm IoT**: số đo cập nhật mỗi 5 giây, sơ đồ luồng sáng lên theo từng gói tin.
3. Trên Wokwi trạm: gạt công tắc sang **Thủ công**, vặn biến trở **PM2.5** lên cao (bấm vào biến trở rồi kéo).
4. Khoảng 10–20 giây sau, khi AQI trung bình 1 phút vượt ngưỡng (mặc định 100):
   - trang Trạm IoT chuyển màu, xuất hiện **thư cảnh báo** kèm khuyến nghị theo QĐ 1459;
   - **bảng điện tử** đổi dòng IoT, bật đèn đúng mức màu và kêu còi;
   - **nhật ký** ghi `vuot_nguong`.
5. Vặn biến trở xuống: khi AQI xuống dưới ngưỡng − 10, nhật ký ghi `tro_lai_duoi_nguong` và hệ thống sẵn sàng báo lần sau (chống báo dồn dập: có trễ 10 AQI và tối thiểu 2 phút giữa 2 lần báo).

## Dự phòng khi không dùng được Wokwi
Gói tin y hệt ESP32, chạy từ thư mục gốc dự án:
```
venv\Scripts\python.exe iot\gia_lap\tram_ao.py                 # dao động bình thường theo giờ trong ngày
venv\Scripts\python.exe iot\gia_lap\tram_ao.py --dot-bien 60   # sau 60 giây PM2.5 tăng vọt trong 3 phút
venv\Scripts\python.exe iot\gia_lap\bang_ao.py                 # xem bản tin bảng điện tử nhận được
```

## Cấu hình (`.env`, xem `.env.example`)
| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `IOT_BAT` | `1` | `0` để tắt hẳn module IoT |
| `MQTT_HOST` / `MQTT_PORT` | `broker.hivemq.com` / `1883` | broker MQTT |
| `MQTT_DU_AN` | `dhtnmt-1250080037` | tiền tố chủ đề `airhcm/<dự án>/…`, phải trùng `DU_AN` trong 2 file `.ino` |
| `IOT_KHOA_THIET_BI` | `airhcm-demo-2026` | khóa thiết bị gửi kèm gói tin, phải trùng `KHOA` trong `wokwi_tram/wokwi_tram.ino` |
| `IOT_NGUONG_AQI` | `100` | ngưỡng cảnh báo (AQI trung bình 1 phút) |
| `IOT_EMAIL_NHAN` | *(trống)* | trống: thư chỉ lưu Hộp thư đã gửi; điền email: gửi thật (cần SMTP) |

## Định dạng gói tin
Trạm → `airhcm/<dự án>/tram/<mã thiết bị>/do`
```json
{"khoa":"airhcm-demo-2026","ten":"Trạm IoT Quận 3 (mô phỏng)","vi_do":10.784,"kinh_do":106.688,
 "che_do":"tu_dong","pm25":41.0,"pm10":64.3,"nhiet_do":30.5,"do_am":72,"aqi_thiet_bi":82}
```
Hệ thống → `airhcm/<dự án>/bang/aqi` (retained)
```json
{"t":"10:11","tp":{"aqi":49,"muc":"Tốt","muc_i":0,"chat":"PM2.5","ngay":"2026-10-20","pm25":24.3},
 "iot":{"ma":"IOT01","aqi":162,"muc":"Xấu","muc_i":3,"tuoi_giay":3}}
```
Mã thiết bị chỉ gồm chữ, số, `_`, `-` (tối đa 30 ký tự). Backend loại các gói tin sai khóa, sai mã hoặc có giá trị ngoài khoảng hợp lệ (PM2.5 0–1000, PM10 0–2000, nhiệt độ −20–70 °C, độ ẩm 0–100%). Tên thiết bị bị bỏ ký tự HTML trước khi lưu.

## API
`GET /api/v1/iot/trang-thai` · `/iot/thiet-bi` · `/iot/{ma}/lich-su?phut=30` · `/iot/canh-bao` · `/iot/nhat-ky` · `/iot/bang-dien-tu`

## Giới hạn và hướng triển khai thật
- **Broker công cộng** thì ai cũng đọc và ghi được chủ đề. Trường `khoa` chỉ chặn gói tin lạ, **không phải bảo mật thật**. Triển khai thật cần broker riêng (Mosquitto/EMQX) với TLS (cổng 8883) và tài khoản riêng cho từng thiết bị.
- AQI trạm IoT dùng **trung bình 1 phút** để phản ứng nhanh khi trình diễn. AQI giờ chính thức theo QĐ 1459 dùng **NowCast 12 giờ**, cần lưu chuỗi đủ dài.
- Wokwi không có cảm biến bụi, nên 2 biến trở đóng vai cảm biến. Khi lắp PMS5003 thật (UART), chỉ cần thay hàm `docCamBien()`; định dạng gói tin và toàn bộ backend giữ nguyên.
- Xóa dữ liệu mô phỏng khi cần làm sạch trước buổi trình diễn (psql):
  `DELETE FROM du_lieu_iot; DELETE FROM thu_da_gui WHERE loai = 'iot';`
