"""Kịch bản "nếu đầu vào thay đổi thì PM2.5 ước lượng thay đổi thế nào" (v3.9).

Dùng mô hình ƯỚC LƯỢNG TRONG NGÀY (hồi quy tuyến tính + Random Forest) vì chỉ mô hình này có các biến đầu vào
(NO₂, CO, SO₂, O₃, nhiệt độ, độ ẩm, gió, mưa) để người dùng thay đổi. Mô hình "dự báo ngày mai" chỉ dùng PM2.5 quá khứ.

Điều cần nói rõ khi trình bày:
  * Đây là ĐỘ NHẠY của mô hình thống kê, KHÔNG phải quan hệ nhân quả (ví dụ giảm NO₂ vệ tinh không có nghĩa là giảm phát thải).
  * Mỗi lần chỉ đổi biến của ngày đó; các biến trễ (PM2.5 hôm qua...) giữ nguyên, nên phản ứng thường nhỏ vì PM2.5 hôm qua là đặc trưng mạnh nhất.
  * Giá trị đầu vào bị giới hạn trong khoảng 1%–99% đã gặp khi huấn luyện (Random Forest không ngoại suy được).
"""

import numpy as np
import pandas as pd

BIEN = {  # he_so: nhân với giá trị gốc để hiển thị cho người dùng
    "no2_mean": {"ten": "NO₂ (vệ tinh)", "don_vi": "×10⁻⁴ mol/m²", "he_so": 1e4},
    "co_gee": {"ten": "CO (vệ tinh)", "don_vi": "×10⁻² mol/m²", "he_so": 1e2},
    "so2_gee": {"ten": "SO₂ (vệ tinh)", "don_vi": "×10⁻⁴ mol/m²", "he_so": 1e4},
    "o3_mean": {"ten": "O₃ mặt đất", "don_vi": "µg/m³", "he_so": 1.0},
    "nhiet_do_mean": {"ten": "Nhiệt độ", "don_vi": "°C", "he_so": 1.0},
    "do_am_mean": {"ten": "Độ ẩm", "don_vi": "%", "he_so": 1.0},
    "gio_toc_do_mean": {"ten": "Tốc độ gió", "don_vi": "km/h", "he_so": 1.0},
    "mua_tong": {"ten": "Lượng mưa", "don_vi": "mm", "he_so": 1.0},
}
GHI_CHU = ("Kết quả là độ nhạy của mô hình thống kê học trên số liệu CAMS, không phải quan hệ nhân quả. "
           "Chỉ đổi biến của chính ngày đó; PM2.5 các ngày trước giữ nguyên nên mức phản ứng thường nhỏ. "
           "Giá trị nhập bị giới hạn trong khoảng đã gặp khi huấn luyện.")


def tao_hang_nen(df_dac_trung: pd.DataFrame, features):
    """Ngày GẦN NHẤT có đủ mọi đặc trưng (NO₂/CO/SO₂ vệ tinh trễ vài tuần nên thường cũ hơn hôm nay)."""
    d = df_dac_trung.dropna(subset=list(features) + ["pm25_mean"])
    if d.empty:
        return None, None
    r = d.iloc[-1]
    return {f: float(r[f]) for f in features}, r["ngay_do"]


def _du_doan(mo_hinh, features, hang):
    X = pd.DataFrame([hang])[list(features)]
    return {ten: float(m.predict(X)[0]) for ten, m in mo_hinh.items()}


def ap_dung_thay_doi(hang, thay_doi, khoang):
    """thay_doi: {biến: giá trị mới (đơn vị gốc)}. Trả (hàng mới, danh sách biến bị kẹp vào khoảng huấn luyện)."""
    moi, kep = dict(hang), []
    for k, v in (thay_doi or {}).items():
        if k not in BIEN:
            raise ValueError(f"Biến không hỗ trợ: {k}")
        lo, hi = khoang[k]["p01"], khoang[k]["p99"]
        v = float(v)
        if v < lo or v > hi:
            kep.append(k)
        moi[k] = float(min(max(v, lo), hi))
    moi["nhietdo_x_doam"] = moi["nhiet_do_mean"] * moi["do_am_mean"]
    return moi, kep


def duong_nhay(mo_hinh, features, hang, khoang, so_diem=11):
    """Với mỗi biến: quét đều trong [p01, p99], các biến khác giữ nguyên ở giá trị nền."""
    kq = {}
    for k in BIEN:
        xs = np.linspace(khoang[k]["p01"], khoang[k]["p99"], so_diem)
        pts = []
        for x in xs:
            h, _ = ap_dung_thay_doi(hang, {k: x}, khoang)
            p = _du_doan(mo_hinh, features, h)
            pts.append({"x": float(x), "x_hien_thi": float(x * BIEN[k]["he_so"]), **{t: round(v, 2) for t, v in p.items()}})
        kq[k] = pts
    return kq


def thong_tin_bien(hang, khoang):
    return [{"ma": k, "ten": b["ten"], "don_vi": b["don_vi"], "he_so": b["he_so"], "nen": hang[k],
             "nen_hien_thi": hang[k] * b["he_so"], "min": khoang[k]["p01"], "max": khoang[k]["p99"]} for k, b in BIEN.items()]


# Kịch bản mẫu: vị trí của biến trong khoảng đã gặp khi huấn luyện (0 = mức 1%, 1 = mức 99%), các biến khác giữ nền
KICH_BAN_MAU = {
    "nang_nong": {"ten": "Nắng nóng, khô", "mo_ta": "Nhiệt độ cao nhất, độ ẩm và mưa thấp nhất đã gặp",
                  "vi_tri": {"nhiet_do_mean": 1, "do_am_mean": 0, "mua_tong": 0}},
    "mua_lon": {"ten": "Mưa lớn", "mo_ta": "Mưa và độ ẩm cao nhất, trời mát",
                "vi_tri": {"mua_tong": 1, "do_am_mean": 1, "nhiet_do_mean": 0.2}},
    "gio_manh": {"ten": "Gió mạnh", "mo_ta": "Tốc độ gió cao nhất đã gặp", "vi_tri": {"gio_toc_do_mean": 1}},
    "gio_lang": {"ten": "Gió lặng", "mo_ta": "Tốc độ gió thấp nhất đã gặp", "vi_tri": {"gio_toc_do_mean": 0}},
    "o_nhiem_cao": {"ten": "Khí ô nhiễm tăng cao", "mo_ta": "NO₂, CO, SO₂ vệ tinh ở mức cao nhất",
                    "vi_tri": {"no2_mean": 1, "co_gee": 1, "so2_gee": 1}},
    "khong_khi_sach": {"ten": "Không khí sạch", "mo_ta": "NO₂, CO, SO₂, O₃ ở mức thấp nhất",
                       "vi_tri": {"no2_mean": 0, "co_gee": 0, "so2_gee": 0, "o3_mean": 0}},
}
NGUONG_QCVN_PM25 = 50.0   # QCVN 05:2023/BTNMT, trung bình 24 giờ
NGUONG_WHO_PM25 = 15.0    # Khuyến nghị WHO 2021, trung bình 24 giờ


def thay_doi_mau(ma, khoang):
    return {k: khoang[k]["p01"] + t * (khoang[k]["p99"] - khoang[k]["p01"]) for k, t in KICH_BAN_MAU[ma]["vi_tri"].items()}


def danh_gia(kq, chi_so_mo_hinh, muc_aqi, tinh_aqi):
    """Nhận xét kết quả kịch bản và mức độ tin cậy, viết bằng lời cho người đọc phổ thông.
    chi_so_mo_hinh: meta['danh_gia']['mo_hinh']['uoc_luong_trong_ngay'] (RMSE, phân vị sai số trên tập kiểm tra)."""
    rf_cs = chi_so_mo_hinh.get("random_forest") or {}
    tt_cs = chi_so_mo_hinh.get("hoi_quy_tuyen_tinh") or {}
    rmse = float(np.mean([x for x in (rf_cs.get("RMSE"), tt_cs.get("RMSE")) if x is not None] or [np.nan]))
    nen = float(np.mean(list(kq["nen"].values())))
    moi = float(np.mean(list(kq["kich_ban"].values())))
    dl = moi - nen
    pt = dl / nen * 100 if nen else 0.0
    aqi_nen, aqi_moi = tinh_aqi(pm25=nen)[0], tinh_aqi(pm25=moi)[0]
    m_nen, m_moi = muc_aqi(aqi_nen) or {}, muc_aqi(aqi_moi) or {}

    nx = []
    if abs(dl) < 0.05:
        nx.append("Kịch bản không làm PM2.5 ước lượng thay đổi.")
    else:
        nx.append(f"PM2.5 ước lượng {'tăng' if dl > 0 else 'giảm'} {abs(dl):.1f} µg/m³ ({pt:+.0f}%), "
                  f"từ {nen:.1f} lên {moi:.1f} µg/m³." if dl > 0 else
                  f"PM2.5 ước lượng giảm {abs(dl):.1f} µg/m³ ({pt:+.0f}%), từ {nen:.1f} xuống {moi:.1f} µg/m³.")
    if m_nen.get("muc") != m_moi.get("muc"):
        nx.append(f"Mức chất lượng không khí chuyển từ “{m_nen.get('muc')}” (AQI {aqi_nen}) sang “{m_moi.get('muc')}” (AQI {aqi_moi}).")
    else:
        nx.append(f"Mức chất lượng không khí giữ nguyên “{m_moi.get('muc')}” (AQI {aqi_nen} → {aqi_moi}).")
    if moi > NGUONG_QCVN_PM25:
        nx.append(f"Vượt ngưỡng QCVN 05:2023 ({NGUONG_QCVN_PM25:.0f} µg/m³ trung bình 24 giờ) — cần hạn chế hoạt động ngoài trời.")
    elif moi > NGUONG_WHO_PM25:
        nx.append(f"Trong ngưỡng QCVN 05:2023 ({NGUONG_QCVN_PM25:.0f} µg/m³) nhưng gấp {moi / NGUONG_WHO_PM25:.1f} lần khuyến nghị WHO ({NGUONG_WHO_PM25:.0f} µg/m³).")
    else:
        nx.append(f"Đạt khuyến nghị WHO ({NGUONG_WHO_PM25:.0f} µg/m³).")

    # ---- Độ tin cậy
    ly_do, diem = [], 0
    rf_dl, tt_dl = kq["chenh_lech"].get("random_forest", 0), kq["chenh_lech"].get("tuyen_tinh", 0)
    if not np.isnan(rmse):
        if abs(dl) < 0.5 * rmse:
            ly_do.append(f"Mức thay đổi ({abs(dl):.1f} µg/m³) nhỏ hơn một nửa sai số thường gặp của mô hình (±{rmse:.1f} µg/m³): "
                         "chưa đủ để khẳng định PM2.5 thật sự thay đổi.")
        elif abs(dl) < rmse:
            ly_do.append(f"Mức thay đổi ({abs(dl):.1f} µg/m³) xấp xỉ sai số mô hình (±{rmse:.1f} µg/m³): chỉ nên xem là xu hướng.")
            diem += 1
        else:
            ly_do.append(f"Mức thay đổi ({abs(dl):.1f} µg/m³) lớn hơn sai số mô hình (±{rmse:.1f} µg/m³).")
            diem += 2
    if abs(rf_dl) < 0.05 and abs(tt_dl) < 0.05:
        pass
    elif kq.get("hai_mo_hinh_trai_chieu"):
        ly_do.append(f"Hai mô hình cho kết quả TRÁI CHIỀU (Random Forest {rf_dl:+.1f}, hồi quy tuyến tính {tt_dl:+.1f} µg/m³).")
        diem -= 2
    else:
        lech = abs(rf_dl - tt_dl)
        ly_do.append(f"Hai mô hình cùng chiều (Random Forest {rf_dl:+.1f}, hồi quy tuyến tính {tt_dl:+.1f} µg/m³"
                     + (", lệch nhau khá nhiều)." if lech > max(abs(rf_dl), abs(tt_dl)) * 0.6 else ")."))
        diem += 1 if lech <= max(abs(rf_dl), abs(tt_dl)) * 0.6 else 0
    if kq.get("bien_bi_gioi_han"):
        ly_do.append("Có giá trị vượt khoảng đã gặp khi huấn luyện nên đã bị giới hạn: mô hình không dự đoán được ngoài khoảng này.")
        diem -= 1
    ly_do.append("Đây là độ nhạy của mô hình thống kê, không phải quan hệ nhân quả; chỉ đổi điều kiện của chính ngày đó.")
    muc = "cao" if diem >= 3 else "trung_binh" if diem >= 1 else "thap"
    if not np.isnan(rmse) and abs(dl) < 0.5 * rmse:
        muc = "thap"   # thay đổi nằm trong nhiễu của mô hình: hai mô hình đồng thuận cũng không làm kết luận đáng tin hơn

    khoang = None
    pv = rf_cs.get("phan_vi_sai_so")
    if pv and pv.get("q10") is not None:
        rf = kq["kich_ban"]["random_forest"]
        khoang = {"thap": round(max(0.0, rf + pv["q10"]), 1), "cao": round(rf + pv["q90"], 1)}
    return {"pm25_nen": round(nen, 1), "pm25_kich_ban": round(moi, 1), "chenh_lech": round(dl, 2), "phan_tram": round(pt, 1),
            "aqi_nen": aqi_nen, "aqi_kich_ban": aqi_moi, "muc_nen": m_nen.get("muc"), "muc_kich_ban": m_moi.get("muc"),
            "khuyen_nghi": {"nguoi_binh_thuong": m_moi.get("nguoi_binh_thuong"), "nhom_nhay_cam": m_moi.get("nhom_nhay_cam")},
            "nhan_xet": nx, "tin_cay": {"muc": muc, "ly_do": ly_do, "rmse_mo_hinh": None if np.isnan(rmse) else round(rmse, 2),
                                        "khoang_80": khoang}}


def chay_kich_ban(mo_hinh, features, hang, khoang, thay_doi):
    moi, kep = ap_dung_thay_doi(hang, thay_doi, khoang)
    nen, kb = _du_doan(mo_hinh, features, hang), _du_doan(mo_hinh, features, moi)
    return {"nen": {k: round(v, 2) for k, v in nen.items()}, "kich_ban": {k: round(v, 2) for k, v in kb.items()},
            "chenh_lech": {k: round(kb[k] - nen[k], 2) for k in nen}, "bien_bi_gioi_han": kep,
            "hai_mo_hinh_trai_chieu": bool(len(nen) == 2 and np.sign(kb["random_forest"] - nen["random_forest"]) *
                                           np.sign(kb["tuyen_tinh"] - nen["tuyen_tinh"]) < 0)}
