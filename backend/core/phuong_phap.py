"""Hồ sơ phương pháp của hệ thống (một nguồn duy nhất cho API /api/v1/phuong-phap, trang Phương pháp và báo cáo).

Trả lời 4 câu hỏi:
  1. Mỗi chỉ số được dự báo bằng mô hình nào, ở tầm dự báo nào (MO_HINH).
  2. Độ phân giải không gian – thời gian của dữ liệu qua từng khâu (NGUON, CHUOI_DO_PHAN_GIAI).
  3. Các nguồn dữ liệu khác nhau được ghép với nhau thế nào (BUOC_TICH_HOP).
  4. Mô hình được đánh giá thế nào và có đạt hay không (QUY_TRINH_DANH_GIA, ket_luan()).

Số liệu đánh giá KHÔNG ghi tay ở đây: mọi chỉ số được đọc từ tệp kết quả do script huấn luyện/đánh giá ghi ra (cột `tep`),
nên khi huấn luyện lại thì trang web tự cập nhật. Kiểm thử tests/test_phuong_phap.py bảo đảm danh sách đặc trưng khai báo
ở đây khớp với mô hình đang chạy.
"""
from __future__ import annotations

import json
import math
import time

from core import config

THU_MUC = config.PROJECT_ROOT / "models"

# ---------------------------------------------------------------- 2. Nguồn dữ liệu và độ phân giải gốc
NGUON = [
    {"ma": "cams", "ten": "CAMS (Copernicus, qua Open-Meteo)", "chi_so": "PM2.5, PM10, O3, CO, NO2, SO2 (µg/m³)",
     "khong_gian": "Lưới ≈ 0,4° (≈ 44 km)", "thoi_gian": "Theo giờ", "do_tre": "Gần thời gian thực, có dự báo",
     "lay_theo_vi_tri": "Giá trị của ô lưới chứa tọa độ điểm ước tính", "mui_gio": "Yêu cầu trả về theo giờ Việt Nam (GMT+7)",
     "gop_thoi_gian": "Trung bình 24 giờ → giá trị ngày", "don_vi": "µg/m³, dùng trực tiếp cho VN_AQI",
     "bang": "du_lieu_tram_mat_dat", "ma_nguon": "data_pipeline/download_openmeteo_data.py"},
    {"ma": "era5", "ten": "Khí tượng ECMWF IFS / ERA5 (qua Open-Meteo)", "chi_so": "Nhiệt độ, độ ẩm, gió 10 m, mưa, áp suất",
     "khong_gian": "Lưới ≈ 9 km (IFS, từ 2017) đến 0,25° (≈ 28 km, ERA5)", "thoi_gian": "Theo giờ", "do_tre": "Khoảng 5 ngày",
     "lay_theo_vi_tri": "Giá trị của ô lưới chứa tọa độ điểm ước tính", "mui_gio": "GMT+7",
     "gop_thoi_gian": "Trung bình 24 giờ; riêng lượng mưa lấy TỔNG ngày", "don_vi": "°C, %, km/h, mm",
     "bang": "du_lieu_tram_mat_dat (cùng dòng với CAMS)", "ma_nguon": "data_pipeline/download_openmeteo_data.py"},
    {"ma": "s5p", "ten": "Sentinel-5P TROPOMI (qua Google Earth Engine)", "chi_so": "Cột khí NO2, CO, SO2 (mol/m²)",
     "khong_gian": "Điểm ảnh ≈ 3,5–7 × 5,5 km; lấy mẫu lại lưới 1,1 km trên GEE", "thoi_gian": "1 lần/ngày (khi vệ tinh bay qua)", "do_tre": "1–2 tuần",
     "lay_theo_vi_tri": "Trung bình các điểm ảnh trong vòng tròn bán kính 2 km quanh điểm", "mui_gio": "Theo ngày chụp",
     "gop_thoi_gian": "Một ảnh/ngày; ngày mây che (không có ảnh) để trống",
     "don_vi": "mol/m² (lượng khí cả cột) — KHÔNG đổi sang µg/m³, không đưa vào VN_AQI",
     "bang": "du_lieu_gee_tphcm", "ma_nguon": "data_pipeline/download_gee_data.py"},
    {"ma": "openaq", "ten": "OpenAQ (trạm đo mặt đất)", "chi_so": "PM2.5 đo thật (µg/m³)",
     "khong_gian": "3 điểm đo (tọa độ chính xác)", "thoi_gian": "Theo giờ", "do_tre": "Vài giờ",
     "lay_theo_vi_tri": "Đúng vị trí trạm; ghép với CAMS cùng tọa độ để đối chiếu", "mui_gio": "UTC → đổi sang GMT+7, làm tròn đầu giờ",
     "gop_thoi_gian": "Trung bình ngày chỉ tính khi có ≥ 18/24 giờ đo", "don_vi": "µg/m³",
     "bang": "tram_do_that, do_that_gio", "ma_nguon": "data_pipeline/tai_tram_that.py"},
    {"ma": "ranh_gioi", "ten": "Ranh giới hành chính (sau 01/7/2025)", "chi_so": "168 phường/xã (đa giác)",
     "khong_gian": "Đa giác vector", "thoi_gian": "Tĩnh", "do_tre": "—",
     "lay_theo_vi_tri": "ST_Contains: điểm nào thuộc phường nào", "mui_gio": "—", "gop_thoi_gian": "—", "don_vi": "EPSG:4326",
     "bang": "phuong_xa", "ma_nguon": "data_pipeline/nap_ranh_gioi.py"},
]

# Độ phân giải qua từng khâu: dữ liệu gốc → lưu trữ → mô hình → hiển thị
CHUOI_DO_PHAN_GIAI = [
    {"khau": "1. Dữ liệu gốc", "khong_gian": "Lưới 44 km (CAMS), 9–28 km (khí tượng), ≈ 3,5–7 × 5,5 km (vệ tinh), 3 điểm đo thật",
     "thoi_gian": "Giờ (CAMS, ERA5, OpenAQ); ngày (vệ tinh)"},
    {"khau": "2. Lưu trong CSDL", "khong_gian": "17 điểm ước tính (Point, PostGIS) + 3 điểm đo thật",
     "thoi_gian": "Ngày (bảng số liệu chính); giờ (bộ đệm giờ cho mô hình 24 h, số đo thật)"},
    {"khau": "3. Đầu vào mô hình", "khong_gian": "Trung bình thành phố, từng điểm, hoặc điểm CMT8",
     "thoi_gian": "Giờ (dự báo 1–24 h); ngày (ngày mai, 7 ngày); tháng (1–6 tháng)"},
    {"khau": "4. Hiển thị", "khong_gian": "168 phường/xã và lưới nội suy IDW 40 × 40",
     "thoi_gian": "Giờ, ngày, tháng tùy trang"},
]

# ---------------------------------------------------------------- 3. Tích hợp đa nguồn
BUOC_TICH_HOP = [
    {"buoc": "Thu thập", "mo_ta": "Gọi API từng nguồn cho từng điểm ước tính đang hoạt động, tự lấy bù các ngày còn thiếu.",
     "ma_nguon": "data_pipeline/dong_bo_hang_ngay.py"},
    {"buoc": "Đồng bộ không gian", "mo_ta": "Mọi nguồn được quy về tọa độ của 17 điểm: lưới CAMS/ERA5 lấy ô chứa điểm; "
     "vệ tinh lấy trung bình vòng 2 km; điểm thuộc phường nào xác định bằng ST_Contains.", "ma_nguon": "services/ranh_gioi.py"},
    {"buoc": "Đồng bộ thời gian", "mo_ta": "Đổi về giờ Việt Nam (GMT+7), làm tròn đầu giờ, rồi gộp thành ngày: trung bình, "
     "riêng mưa lấy tổng; ngày đo thật cần ≥ 18 giờ có số liệu.", "ma_nguon": "data_pipeline/download_openmeteo_data.py"},
    {"buoc": "Chuẩn hóa đơn vị", "mo_ta": "Nồng độ giữ µg/m³; cột khí vệ tinh (mol/m²) lưu bảng riêng, không trộn vào VN_AQI.",
     "ma_nguon": "ml/tinh_aqi.py"},
    {"buoc": "Kiểm soát chất lượng", "mo_ta": "Loại giá trị âm và mã lỗi thiết bị ≥ 900 µg/m³; kiểm tra khoảng hợp lý, "
     "ngày thiếu, giá trị đứng yên; ngày thiếu để trống, không nội suy nhân tạo.", "ma_nguon": "data_pipeline/kiem_tra_du_lieu.py"},
    {"buoc": "Ghép và lưu", "mo_ta": "Ghép theo khóa (điểm, ngày); ràng buộc duy nhất (tram_id, ngay_do) + INSERT … ON CONFLICT "
     "DO UPDATE nên nạp lại không sinh bản ghi trùng.", "ma_nguon": "backend/sql/bang_du_lieu.sql"},
    {"buoc": "Ghép cho mô hình", "mo_ta": "Nối các nguồn theo ngày (left join trên lịch liên tục) để độ trễ đúng nghĩa; "
     "mô hình chỉ thấy thông tin có trước thời điểm dự báo.", "ma_nguon": "ml/mo_hinh_tram_that.py"},
]

# ---------------------------------------------------------------- 4. Quy trình đánh giá
QUY_TRINH_DANH_GIA = [
    "Chia theo thời gian: huấn luyện trên đoạn trước, kiểm tra trên đoạn sau (không xáo trộn) để không rò rỉ tương lai.",
    "So với mốc tham chiếu đơn giản (persistence: \"mai bằng hôm nay\"); thước đo chính là kỹ năng = 1 − RMSE mô hình / RMSE mốc.",
    "Khoảng tin cậy 95% của kỹ năng bằng bootstrap theo khối 7 ngày (giữ tự tương quan).",
    "Kiểm chéo cuốn chiếu và tách mùa khô (12–4) / mùa mưa (5–11).",
    "Dự báo xác suất: tỉ lệ bao PICP của khoảng 80% và điểm Brier so với tần suất khí hậu.",
    "Đối chiếu với số đo thật OpenAQ để biết giới hạn của chính dữ liệu huấn luyện.",
]
TIEU_CHI = {
    "dat": "Tốt hơn mốc có ý nghĩa thống kê (cận dưới KTC 95% > 0) → dùng để dự báo",
    "tham_khao": "Tốt hơn mốc nhưng khoảng tin cậy còn chứa 0 → hiển thị kèm ghi chú tham khảo",
    "chua_dat": "Chưa tốt hơn mốc → chỉ dùng cho mục đích khác (so sánh tương đối giữa khu vực, thử nghiệm)",
    "chua_kiem_dinh": "Tốt hơn mốc trên tập kiểm tra, chưa tính khoảng tin cậy",
}


def ket_luan(ky_nang, thap=None, cao=None) -> str:
    """Quy tắc đưa mô hình vào vận hành (hàm thuần, có kiểm thử)."""
    if ky_nang is None:
        return "chua_kiem_dinh"
    if thap is not None and thap > 0:
        return "dat"
    if ky_nang <= 0:
        return "chua_dat"
    return "tham_khao" if thap is not None else "chua_kiem_dinh"


# ---------------------------------------------------------------- Đọc chỉ số từ tệp kết quả
def _json(ten):
    f = THU_MUC / ten
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def _meta():
    f = THU_MUC / "model_metadata.pkl"
    if not f.exists():
        return None
    import joblib
    return joblib.load(f)


def _r(x, n=3):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), n)


def _cs(ky_nang, thap=None, cao=None, so_mau=None, kiem_tra_tu=None, them=None, thuoc_do="Kỹ năng so với persistence",
        loai_khoang="KTC 95% (bootstrap khối 7 ngày)"):
    k, t, c = _r(ky_nang), _r(thap), _r(cao)
    return {"thuoc_do": thuoc_do, "ky_nang": k, "khoang": [t, c] if t is not None else None,
            "loai_khoang": loai_khoang if t is not None else None, "so_mau_kiem_tra": so_mau,
            "kiem_tra_tu": str(kiem_tra_tu)[:10] if kiem_tra_tu else None, "ket_luan": ket_luan(k, t, c), **(them or {})}


def cs_gio():
    d = _json("du_bao_gio_chi_so.json")
    if not d:
        return None
    cv = [x["ky_nang_so_voi_persistence"] for x in d.get("kiem_tra_cheo", [])]
    t = d["tong"]
    return _cs(t["ky_nang_so_voi_persistence"], min(cv) if cv else None, max(cv) if cv else None, None, d.get("kiem_tra_tu"),
               {"RMSE": _r(t["rmse"], 2), "MAE": _r(t["mae"], 2), "so_mau_tong": d.get("so_mau"),
                "theo_buoc": {h: _r(v["ky_nang_so_voi_persistence"]) for h, v in d.get("theo_buoc", {}).items()}},
               loai_khoang=f"Thấp nhất – cao nhất của {len(cv)} lần kiểm chéo theo thời gian")


def cs_ngay(bai_toan="du_bao_ngay_mai"):
    m = _meta()
    x = ((m or {}).get("danh_gia", {}).get("mo_hinh", {}) or {}).get(bai_toan)
    if not x:
        return None
    rf = x["random_forest"]
    ci = rf.get("ky_nang_ci95_bootstrap") or {}
    them = {"RMSE": _r(rf["RMSE"], 2), "MAE": _r(rf["MAE"], 2), "R2": _r(rf.get("R2"))}
    gop = (x.get("kiem_cheo_cuon_chieu") or {}).get("gop")
    if bai_toan == "uoc_luong_trong_ngay" and gop and gop.get("ci95"):
        # mẫu kiểm tra cuối chỉ 124 ngày → dùng kiểm chéo cuốn chiếu (5 lần, 411 ngày) làm kết luận chính
        return _cs(gop["ky_nang"], gop["ci95"]["thap"], gop["ci95"]["cao"], gop.get("so_ngay"), None,
                   them | {"ky_nang_tap_kiem_tra_cuoi": _r(rf["ky_nang_so_voi_hom_qua"])},
                   loai_khoang="KTC 95% gộp của kiểm chéo cuốn chiếu 5 lần")
    return _cs(rf["ky_nang_so_voi_hom_qua"], ci.get("thap"), ci.get("cao"), x.get("so_mau_kiem_tra"), x.get("kiem_tra_tu"), them)


def cs_da_chat(chat):
    d = _json("du_bao_da_chat.json")
    c = (d or {}).get("chat", {}).get(chat)
    if not c:
        return None
    ten = c["mo_hinh_chon"]
    m = c["mo_hinh"][ten]
    ci = m.get("ky_nang_ci95") or {}
    return _cs(m["ky_nang"], ci.get("thap"), ci.get("cao"), c.get("so_ngay_kiem_tra"), c.get("kiem_tra_tu"),
               {"RMSE": m["RMSE"], "MAE": m["MAE"], "mo_hinh_chon": ten,
                "theo_mua": {k: v.get("ky_nang") for k, v in m.get("theo_mua", {}).items()}})


def cs_xac_suat():
    d = _json("danh_gia_xac_suat.json")
    if not d:
        return None
    who = d.get("xac_suat", {}).get("who_15", {})
    return _cs(d.get("ky_nang_so_voi_hom_qua"), None, None, d.get("so_ngay"), d.get("tu"),
               {"MAE": d.get("MAE"), "PICP_80": d.get("PICP_80"), "Brier_WHO15": who.get("Brier"), "BSS_WHO15": who.get("BSS"),
                "ghi_chu": "Ngày thật sau mốc huấn luyện (kiểm chứng ngoài mẫu)"})


_DEM_THANG = {"t": 0, "v": None}


def cs_thang():
    """Kiểm chứng ngược dự báo theo tháng (tính từ CSDL, lưu đệm 1 giờ)."""
    if _DEM_THANG["v"] is None or time.time() - _DEM_THANG["t"] > 3600:
        try:
            from predict import du_bao_theo_thang
            dg = (du_bao_theo_thang(1) or {}).get("danh_gia")
        except Exception:
            dg = None
        _DEM_THANG.update(t=time.time(), v=dg or {})
    dg = _DEM_THANG["v"]
    if not dg:
        return None
    return _cs(dg.get("ky_nang"), None, None, dg.get("so_thang_thu"), None,
               {"MAE": dg.get("MAE_khi_hau_hoc"), "MAE_moc": dg.get("MAE_thang_sau_bang_thang_truoc"),
                "ghi_chu": "Kiểm chứng ngược từng tháng lịch sử, bỏ chính năm đang thử; mốc = \"tháng sau bằng tháng trước\""},
               thuoc_do="Kỹ năng theo MAE so với \"tháng sau = tháng trước\"")


def cs_tram_that():
    d = _json("mo_hinh_tram_that.json")
    if not d:
        return None
    ten = next((k for k in d["mo_hinh"] if k.startswith("Hồi quy")), None)
    m = d["mo_hinh"].get(ten) if ten else None
    if not m:
        return None
    ci = m.get("ky_nang_ci95") or {}
    cams = d["mo_hinh"].get("CAMS thô", {})
    return _cs(m["ky_nang"], ci.get("thap"), ci.get("cao"), d.get("so_ngay_kiem_tra"), d.get("kiem_tra_tu"),
               {"RMSE": m["RMSE"], "MAE": m["MAE"], "ky_nang_CAMS_tho": cams.get("ky_nang")})


def cs_diem():
    d = _json("diem_chi_so.json")
    if not d:
        return None
    rf = d["random_forest"]
    ci = rf.get("ky_nang_ci95_bootstrap") or {}
    return _cs(rf["ky_nang_so_voi_hom_qua"], ci.get("thap"), ci.get("cao"), d.get("so_mau_kiem_tra"), d.get("kiem_tra_tu"),
               {"RMSE": _r(rf["RMSE"], 2), "tuong_quan_do_lech_khong_gian": _r(d.get("khong_gian", {}).get("tuong_quan_lech_du_bao_va_that"))})


def cs_noi_suy():
    d = _json("danh_gia_noi_suy.json")
    if not d:
        return None
    k = d["kiem_cheo_idw"]
    return _cs(k.get("ky_nang"), None, None, k.get("so_ngay"), None,
               {"RMSE": k.get("RMSE_idw"), "RMSE_moc": k.get("RMSE_trung_binh_con_lai"), "o_luoi_theo_nam": d.get("o_luoi_theo_nam"),
                "ghi_chu": "Kiểm chéo bỏ một ô lưới; mốc = trung bình các ô còn lại"},
               thuoc_do="Kỹ năng so với \"trung bình các điểm còn lại\"")


def cs_phan_loai():
    d = None
    f = config.PROJECT_ROOT / "ml" / "notebooks" / "ket_qua" / "phan_loai_chi_so.json"
    if f.exists():
        d = json.loads(f.read_text(encoding="utf-8"))
    if not d:
        return None
    rf = next((m for m in d["mo_hinh"] if m["model"].startswith("Random Forest")), None)
    if not rf:
        return None
    return {"thuoc_do": "Phân loại (ngưỡng %g µg/m³)" % d.get("nguong_ugm3", 25), "ky_nang": None,
            "so_mau_kiem_tra": d.get("so_ngay_test"), "kiem_tra_tu": None, "ket_luan": "thuc_nghiem",
            "khoang": None, "loai_khoang": None,
            "Recall": rf["Recall"], "Precision": rf["Precision"], "ROC_AUC": rf["ROC_AUC"], "Accuracy": rf["Accuracy"]}


# ---------------------------------------------------------------- 1. Mô hình theo chỉ số và tầm dự báo
def _dac_trung_gio():
    from services.du_bao_gio import DAC_TRUNG
    return DAC_TRUNG


def _dac_trung_ngay():
    m = _meta()
    return (m or {}).get("features_du_bao_ngay_mai")


def _dac_trung_trong_ngay():
    m = _meta()
    return (m or {}).get("features")


MO_HINH = [
    {"ma": "gio", "chi_so": "PM2.5", "tam": "1–24 giờ tới", "nhom": "Ngắn hạn", "do_phan_giai_ra": "Theo giờ · trung tâm TP",
     "mo_hinh": "HistGradientBoosting (một mô hình cho cả 24 bước, dự báo mức thay đổi so với hiện tại)",
     "doi_chung": "Persistence, \"cùng giờ hôm qua\"", "du_lieu": "CAMS PM2.5/PM10 + ERA5 theo giờ, 08/2022 →",
     "dac_trung": _dac_trung_gio, "chi_so_danh_gia": cs_gio, "api": "/api/v1/du-bao-gio", "trang": "du-bao.html",
     "ma_nguon": "ml/train_du_bao_gio.py"},
    {"ma": "trong_ngay", "chi_so": "PM2.5", "tam": "Ước lượng trong ngày", "nhom": "Ước lượng", "do_phan_giai_ra": "Theo ngày · trung bình TP",
     "mo_hinh": "Random Forest (26 đặc trưng khí tượng, vệ tinh, độ trễ)", "doi_chung": "Hồi quy tuyến tính, cây quyết định, \"hôm nay = hôm qua\"",
     "du_lieu": "CAMS + ERA5 + Sentinel-5P theo ngày", "dac_trung": _dac_trung_trong_ngay,
     "chi_so_danh_gia": lambda: cs_ngay("uoc_luong_trong_ngay"), "api": "/api/v1/kich-ban", "trang": "kich-ban.html",
     "ma_nguon": "ml/train_model.py"},
    {"ma": "ngay_mai", "chi_so": "PM2.5 (→ VN_AQI)", "tam": "Ngày mai và 7 ngày (lặp nhiều bước)", "nhom": "Ngắn – trung hạn",
     "do_phan_giai_ra": "Theo ngày · trung bình TP", "mo_hinh": "Random Forest (12 đặc trưng chuỗi PM2.5 + lịch)",
     "doi_chung": "Hồi quy tuyến tính, \"mai = hôm nay\", trung bình 7 ngày", "du_lieu": "CAMS PM2.5 theo ngày",
     "dac_trung": _dac_trung_ngay, "chi_so_danh_gia": lambda: cs_ngay("du_bao_ngay_mai"), "api": "/api/v1/du-bao-nhieu-ngay",
     "trang": "du-bao.html", "ma_nguon": "ml/train_model.py"},
    {"ma": "xac_suat", "chi_so": "Xác suất PM2.5 vượt ngưỡng", "tam": "Ngày mai – 7 ngày", "nhom": "Xác suất",
     "do_phan_giai_ra": "Theo ngày · trung bình TP", "mo_hinh": "Phân vị sai số của Random Forest (khoảng 80%) → xác suất vượt WHO 15 / QCVN 45",
     "doi_chung": "Tần suất khí hậu", "du_lieu": "Sai số của mô hình trên tập kiểm tra", "dac_trung": None,
     "chi_so_danh_gia": cs_xac_suat, "api": "/api/v1/danh-gia-xac-suat", "trang": "du-bao.html", "ma_nguon": "ml/danh_gia_xac_suat.py"},
    {"ma": "pm25_ngay", "chi_so": "PM2.5", "tam": "Ngày mai", "nhom": "Ngắn hạn – đa chất", "do_phan_giai_ra": "Theo ngày · trung bình TP",
     "mo_hinh": "Ridge hoặc Random Forest — hệ thống tự chọn theo KTC 95%", "doi_chung": "\"Mai = hôm nay\"",
     "du_lieu": "CAMS theo ngày", "dac_trung": lambda: __import__("du_bao_da_chat").DAC_TRUNG,
     "chi_so_danh_gia": lambda: cs_da_chat("pm25"), "api": "/api/v1/du-bao-da-chat", "trang": "du-bao.html", "ma_nguon": "ml/du_bao_da_chat.py"},
    {"ma": "pm10_ngay", "chi_so": "PM10", "tam": "Ngày mai", "nhom": "Ngắn hạn – đa chất", "do_phan_giai_ra": "Theo ngày · trung bình TP",
     "mo_hinh": "Ridge hoặc Random Forest — hệ thống tự chọn theo KTC 95%", "doi_chung": "\"Mai = hôm nay\"",
     "du_lieu": "CAMS theo ngày", "dac_trung": lambda: __import__("du_bao_da_chat").DAC_TRUNG,
     "chi_so_danh_gia": lambda: cs_da_chat("pm10"), "api": "/api/v1/du-bao-da-chat", "trang": "du-bao.html", "ma_nguon": "ml/du_bao_da_chat.py"},
    {"ma": "o3_ngay", "chi_so": "O3 (trung bình ngày)", "tam": "Ngày mai", "nhom": "Ngắn hạn – đa chất", "do_phan_giai_ra": "Theo ngày · trung bình TP",
     "mo_hinh": "Ridge hoặc Random Forest — hệ thống tự chọn theo KTC 95%", "doi_chung": "\"Mai = hôm nay\"",
     "du_lieu": "CAMS theo ngày", "dac_trung": lambda: __import__("du_bao_da_chat").DAC_TRUNG,
     "chi_so_danh_gia": lambda: cs_da_chat("o3"), "api": "/api/v1/du-bao-da-chat", "trang": "du-bao.html", "ma_nguon": "ml/du_bao_da_chat.py"},
    {"ma": "thang", "chi_so": "PM2.5", "tam": "1–6 tháng tới", "nhom": "Dài hạn (xu hướng mùa)", "do_phan_giai_ra": "Theo tháng · trung bình TP",
     "mo_hinh": "Khí hậu học theo tháng + dị thường 30 ngày gần nhất tắt dần 0,5^k", "doi_chung": "\"Tháng sau = tháng trước\"",
     "du_lieu": "Chuỗi PM2.5 ngày ≥ 4 năm", "dac_trung": None, "chi_so_danh_gia": cs_thang, "api": "/api/v1/du-bao-thang",
     "trang": "du-bao.html", "ma_nguon": "ml/predict.py"},
    {"ma": "tram_that", "chi_so": "PM2.5 đo thật (CMT8)", "tam": "Ngày mai", "nhom": "Ngắn hạn – số đo thật", "do_phan_giai_ra": "Theo ngày · 1 điểm đo",
     "mo_hinh": "Ridge / Random Forest học từ số đo thật + CAMS và thời tiết ngày mai", "doi_chung": "\"Mai = hôm nay\", CAMS thô, CAMS bù độ lệch",
     "du_lieu": "OpenAQ theo giờ (≥ 18 giờ/ngày) + CAMS + ERA5", "dac_trung": lambda: __import__("mo_hinh_tram_that").DAC_TRUNG,
     "chi_so_danh_gia": cs_tram_that, "api": "/api/v1/du-bao-tram-that", "trang": "du-bao.html", "ma_nguon": "ml/mo_hinh_tram_that.py"},
    {"ma": "khong_gian", "chi_so": "PM2.5 theo khu vực", "tam": "1–7 ngày", "nhom": "Không gian", "do_phan_giai_ra": "Theo ngày · 168 phường/xã",
     "mo_hinh": "Random Forest chung cho các điểm → nội suy IDW (p = 2) lên lưới và phường/xã", "doi_chung": "\"Mai = hôm nay\" tại từng điểm",
     "du_lieu": "CAMS PM2.5 theo ngày của 16–17 điểm", "dac_trung": _dac_trung_ngay, "chi_so_danh_gia": cs_diem,
     "api": "/api/v1/ban-do-nhiet", "trang": "ban-do-nhiet.html", "ma_nguon": "ml/train_diem.py"},
    {"ma": "noi_suy", "chi_so": "PM2.5 giữa các điểm", "tam": "Cùng thời điểm", "nhom": "Không gian", "do_phan_giai_ra": "Lưới 40 × 40, 168 phường/xã",
     "mo_hinh": "Nội suy IDW (trọng số 1/d², hiệu chỉnh khoảng cách theo vĩ độ)", "doi_chung": "Trung bình các điểm còn lại",
     "du_lieu": "Giá trị các điểm cùng ngày", "dac_trung": None, "chi_so_danh_gia": cs_noi_suy, "api": "/api/v1/ban-do-nhiet",
     "trang": "index.html", "ma_nguon": "backend/services/ban_do_nhiet.py, ml/danh_gia_noi_suy.py"},
    {"ma": "phan_loai", "chi_so": "Ngày vượt 25 µg/m³", "tam": "Ngày mai", "nhom": "Phân loại (thực nghiệm)", "do_phan_giai_ra": "Theo ngày · trung bình TP",
     "mo_hinh": "Random Forest (so với KNN, cây quyết định)", "doi_chung": "KNN k = 7, cây quyết định độ sâu 4",
     "du_lieu": "CAMS + ERA5 theo ngày", "dac_trung": None, "chi_so_danh_gia": cs_phan_loai, "api": "—", "trang": "phuong-phap.html",
     "ma_nguon": "ml/notebooks/02_phan_loai_canh_bao_pm25.ipynb"},
]

KHONG_DU_BAO = {"NO2, CO, SO2": "CAMS có NO2, CO, SO2 nhưng các khí này phát thải tại chỗ (giao thông, công nghiệp) và tồn tại ngắn, lưới 44 km khó đại diện cho nồng độ ở phường; chưa có số đo mặt đất nào của ba khí để kiểm chứng; số liệu vệ tinh là lượng khí cả cột (mol/m²), trễ 1–2 tuần → chưa dự báo, chỉ dùng theo dõi hiện trạng và phân tích độ nhạy."}


def _an_toan(f):
    try:
        return f() if f else None
    except Exception:
        return None


def tong_hop() -> dict:
    mo_hinh = []
    for m in MO_HINH:
        dt = _an_toan(m["dac_trung"])
        mo_hinh.append({k: v for k, v in m.items() if k not in ("dac_trung", "chi_so_danh_gia")}
                       | {"so_dac_trung": len(dt) if dt else None, "dac_trung": list(dt) if dt else None,
                          "danh_gia": _an_toan(m["chi_so_danh_gia"])})
    return {"mo_hinh": mo_hinh, "khong_du_bao": KHONG_DU_BAO, "nguon": NGUON, "chuoi_do_phan_giai": CHUOI_DO_PHAN_GIAI,
            "do_phan_giai_hieu_dung": _json("danh_gia_noi_suy.json"), "tich_hop": BUOC_TICH_HOP,
            "quy_trinh_danh_gia": QUY_TRINH_DANH_GIA, "tieu_chi": TIEU_CHI}
