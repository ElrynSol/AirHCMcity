"""
Tính chỉ số chất lượng không khí Việt Nam (VN_AQI) theo Quyết định 1459/QĐ-TCMT
ngày 12/11/2019 của Tổng cục Môi trường (Bộ TN&MT).
Đã đối chiếu Bảng 1, 2, 4, 5 với bản PDF trên cem.gov.vn (10/2026).

- AQI thành phần: nội suy tuyến tính trong bảng giá trị ngưỡng (Bảng 2 của QĐ 1459).
- AQI tổng hợp = AQI thành phần lớn nhất; chỉ tính khi có ít nhất PM2.5 hoặc PM10
  (QĐ 1459 yêu cầu bắt buộc có một trong hai thông số bụi).
- Phân 6 mức, màu và khuyến nghị sức khỏe theo Bảng 3, Bảng 4 của QĐ 1459.

Dữ liệu của hệ thống:
- PM2.5, PM10: trung bình 24 giờ (AQI ngày) hoặc trung bình trượt (AQI giờ).
- O3: trung bình ngày / trung bình 8 giờ → mặc định tra bảng O3 8 giờ;
  giá trị > 400 µg/m³ (vượt bảng 8h) chuyển sang bảng O3 1 giờ như QĐ quy định.
- NO2, CO, SO2 từ Sentinel-5P là TỔNG CỘT KHÍ QUYỂN (mol/m²), khác đơn vị nồng độ
  mặt đất (µg/m³) nên KHÔNG đưa vào AQI. Bảng ngưỡng của chúng vẫn được khai báo
  để dùng khi có số đo mặt đất thật (gọi qua tinh_aqi_thanh_phan).
"""

# (nồng độ thấp, nồng độ cao, AQI thấp, AQI cao) — đơn vị µg/m³
_MOC_AQI = (0, 50, 100, 150, 200, 300, 400, 500)


def _bang(*moc_nong_do):
    """Ghép các mốc nồng độ BP_i với các mốc AQI I_i thành bảng nội suy."""
    return [(moc_nong_do[i], moc_nong_do[i + 1], _MOC_AQI[i], _MOC_AQI[i + 1])
            for i in range(len(moc_nong_do) - 1)]


BANG_AQI_PM25 = _bang(0, 25, 50, 80, 150, 250, 350, 500)
BANG_AQI_PM10 = _bang(0, 50, 150, 250, 350, 420, 500, 600)
BANG_AQI_O3_1H = _bang(0, 160, 200, 300, 400, 800, 1000, 1200)
BANG_AQI_O3_8H = _bang(0, 100, 120, 170, 210, 400)       # trên 400 dùng bảng 1h
BANG_AQI_NO2_1H = _bang(0, 100, 200, 700, 1200, 2350, 3100, 3850)
BANG_AQI_SO2_1H = _bang(0, 125, 350, 550, 800, 1600, 2100, 2630)
BANG_AQI_CO_1H = _bang(0, 10000, 30000, 45000, 60000, 90000, 120000, 150000)
BANG_AQI_O3 = BANG_AQI_O3_8H  # tên cũ, giữ để tương thích

# Thang 6 mức theo QĐ 1459 (màu chuẩn RGB ghi trong văn bản).
# mau_chu: màu chữ đọc được khi đặt trên nền "mau"; mau_dam: màu chữ khi đặt trên nền trắng.
THANG_AQI = [
    {"tu": 0, "den": 50, "muc": "Tốt", "ten_mau": "Xanh", "rgb": (0, 228, 0),
     "mau": "#00e400", "mau_chu": "#000000", "mau_dam": "#007a00",
     "y_nghia": "Chất lượng không khí tốt, không ảnh hưởng tới sức khỏe.",
     "nguoi_binh_thuong": "Tự do thực hiện các hoạt động ngoài trời.",
     "nhom_nhay_cam": "Tự do thực hiện các hoạt động ngoài trời."},
    {"tu": 51, "den": 100, "muc": "Trung bình", "ten_mau": "Vàng", "rgb": (255, 255, 0),
     "mau": "#ffff00", "mau_chu": "#000000", "mau_dam": "#8a6d00",
     "y_nghia": "Chất lượng không khí ở mức chấp nhận được. Tuy nhiên, đối với những người nhạy cảm "
                "(người già, trẻ em, người mắc các bệnh hô hấp, tim mạch…) có thể chịu những tác động nhất định tới sức khỏe.",
     "nguoi_binh_thuong": "Tự do thực hiện các hoạt động ngoài trời.",
     "nhom_nhay_cam": "Nên theo dõi các triệu chứng như ho hoặc khó thở, nhưng vẫn có thể hoạt động bên ngoài."},
    {"tu": 101, "den": 150, "muc": "Kém", "ten_mau": "Da cam", "rgb": (255, 126, 0),
     "mau": "#ff7e00", "mau_chu": "#000000", "mau_dam": "#b45309",
     "y_nghia": "Những người nhạy cảm gặp phải các vấn đề về sức khỏe, những người bình thường ít ảnh hưởng.",
     "nguoi_binh_thuong": "Những người thấy có triệu chứng đau mắt, ho hoặc đau họng… nên cân nhắc giảm các hoạt động ngoài trời. "
                          "Đối với học sinh, có thể hoạt động bên ngoài, nhưng nên giảm bớt việc tập thể dục kéo dài.",
     "nhom_nhay_cam": "Nên giảm các hoạt động mạnh và giảm thời gian hoạt động ngoài trời. "
                      "Những người mắc bệnh hen suyễn có thể cần sử dụng thuốc thường xuyên hơn."},
    {"tu": 151, "den": 200, "muc": "Xấu", "ten_mau": "Đỏ", "rgb": (255, 0, 0),
     "mau": "#ff0000", "mau_chu": "#ffffff", "mau_dam": "#c50000",
     "y_nghia": "Những người bình thường bắt đầu có các ảnh hưởng tới sức khỏe, "
                "nhóm người nhạy cảm có thể gặp những vấn đề sức khỏe nghiêm trọng hơn.",
     "nguoi_binh_thuong": "Mọi người nên giảm các hoạt động mạnh khi ở ngoài trời, tránh tập thể dục kéo dài "
                          "và nghỉ ngơi nhiều hơn trong nhà.",
     "nhom_nhay_cam": "Nên ở trong nhà và giảm hoạt động mạnh. Nếu cần thiết phải ra ngoài, hãy đeo khẩu trang đạt tiêu chuẩn."},
    {"tu": 201, "den": 300, "muc": "Rất xấu", "ten_mau": "Tím", "rgb": (143, 63, 151),
     "mau": "#8f3f97", "mau_chu": "#ffffff", "mau_dam": "#8f3f97",
     "y_nghia": "Cảnh báo ảnh hưởng tới sức khỏe: mọi người bị ảnh hưởng tới sức khỏe nghiêm trọng hơn.",
     "nguoi_binh_thuong": "Mọi người hạn chế tối đa các hoạt động ngoài trời và chuyển tất cả các hoạt động vào trong nhà. "
                          "Nếu cần thiết phải ra ngoài, hãy đeo khẩu trang đạt tiêu chuẩn.",
     "nhom_nhay_cam": "Nên ở trong nhà và giảm hoạt động mạnh."},
    {"tu": 301, "den": 500, "muc": "Nguy hại", "ten_mau": "Nâu", "rgb": (126, 0, 35),
     "mau": "#7e0023", "mau_chu": "#ffffff", "mau_dam": "#7e0023",
     "y_nghia": "Cảnh báo khẩn cấp về sức khỏe: Toàn bộ dân số bị ảnh hưởng tới sức khỏe tới mức nghiêm trọng.",
     "nguoi_binh_thuong": "Mọi người nên ở trong nhà, đóng cửa ra vào và cửa sổ. "
                          "Nếu cần thiết phải ra ngoài, hãy đeo khẩu trang đạt tiêu chuẩn.",
     "nhom_nhay_cam": "Mọi người nên ở trong nhà, đóng cửa ra vào và cửa sổ. "
                      "Nếu cần thiết phải ra ngoài, hãy đeo khẩu trang đạt tiêu chuẩn."},
]


def tinh_aqi_thanh_phan(nong_do, bang_nguong):
    """AQI_x = (I_i+1 − I_i)/(BP_i+1 − BP_i) × (C_x − BP_i) + I_i, làm tròn số nguyên.
    Trả None nếu không có số liệu; vượt mốc cao nhất của bảng thì trả 500."""
    if nong_do is None:
        return None
    try:
        c = float(nong_do)
    except (TypeError, ValueError):
        return None
    if c != c or c < 0:  # NaN hoặc âm
        return None
    for bp_low, bp_high, i_low, i_high in bang_nguong:
        if c <= bp_high:
            return round((i_high - i_low) / (bp_high - bp_low) * (c - bp_low) + i_low)
    return 500


def tinh_aqi_o3(nong_do, kieu="8h"):
    """AQI của O3. kieu='8h' (trung bình 8 giờ / trung bình ngày) hoặc '1h'.
    Theo QĐ 1459, nồng độ 8h > 400 µg/m³ không có trong bảng 8h → dùng bảng 1h."""
    if kieu == "1h":
        return tinh_aqi_thanh_phan(nong_do, BANG_AQI_O3_1H)
    v = tinh_aqi_thanh_phan(nong_do, BANG_AQI_O3_8H)
    if v == 500:  # vượt bảng 8h
        return tinh_aqi_thanh_phan(nong_do, BANG_AQI_O3_1H)
    return v


def tinh_aqi_tong_hop(pm25=None, pm10=None, o3=None, co=None, no2=None, so2=None, o3_kieu="8h"):
    """
    AQI tổng hợp = AQI thành phần lớn nhất trong PM2.5, PM10, O3. Trả (aqi, chất quyết định).
    Trả (None, None) khi không có PM2.5 lẫn PM10 (QĐ 1459 bắt buộc có thông số bụi).
    Tham số co/no2/so2 được giữ để tương thích lời gọi cũ nhưng KHÔNG dùng
    (số liệu vệ tinh khác đơn vị, xem docstring module).
    """
    cac_aqi = []
    for ten, v in (("PM2.5", tinh_aqi_thanh_phan(pm25, BANG_AQI_PM25)),
                   ("PM10", tinh_aqi_thanh_phan(pm10, BANG_AQI_PM10))):
        if v is not None:
            cac_aqi.append((ten, v))
    if not cac_aqi:
        return None, None

    v = tinh_aqi_o3(o3, o3_kieu)
    if v is not None:
        cac_aqi.append(("O3", v))

    chat_gay_o_nhiem, aqi_max = max(cac_aqi, key=lambda x: x[1])
    return aqi_max, chat_gay_o_nhiem


def muc_aqi(aqi):
    """Trả dict của mức AQI (muc, mau, khuyến nghị…) hoặc None."""
    if aqi is None:
        return None
    for m in THANG_AQI:
        if aqi <= m["den"]:
            return m
    return THANG_AQI[-1]


def phan_loai_aqi(aqi):
    m = muc_aqi(aqi)
    return m["muc"] if m else "Không xác định"


def mau_aqi(aqi):
    m = muc_aqi(aqi)
    return m["mau"] if m else "#98a2b3"


def thang_do_cong_khai():
    """Thang đo + bảng ngưỡng dạng JSON cho API / giao diện."""
    def bang(b):
        return [{"nong_do_tu": lo, "nong_do_den": hi, "aqi_tu": ilo, "aqi_den": ihi} for lo, hi, ilo, ihi in b]
    return {
        "can_cu": "Quyết định 1459/QĐ-TCMT ngày 12/11/2019 của Tổng cục Môi trường",
        "muc": [{k: (list(v) if k == "rgb" else v) for k, v in m.items()} for m in THANG_AQI],
        "bang_nguong_ug_m3": {
            "PM2.5": bang(BANG_AQI_PM25), "PM10": bang(BANG_AQI_PM10),
            "O3_1h": bang(BANG_AQI_O3_1H), "O3_8h": bang(BANG_AQI_O3_8H),
            "NO2_1h": bang(BANG_AQI_NO2_1H), "SO2_1h": bang(BANG_AQI_SO2_1H), "CO_1h": bang(BANG_AQI_CO_1H),
        },
        "ghi_chu": [
            "AQI tổng hợp = giá trị lớn nhất của các AQI thành phần; bắt buộc có PM2.5 hoặc PM10.",
            "Hệ thống tính AQI từ PM2.5, PM10, O3. NO2/CO/SO2 vệ tinh (mol/m²) không cùng đơn vị nên không đưa vào AQI.",
            "Số liệu đầu vào là mô hình CAMS (Open-Meteo), không phải số đo trạm mặt đất chính thức.",
        ],
    }


if __name__ == "__main__":
    aqi, chat = tinh_aqi_tong_hop(pm25=41.2, pm10=44.1)
    print(f"AQI = {aqi}, do chất: {chat}, mức độ: {phan_loai_aqi(aqi)}")
