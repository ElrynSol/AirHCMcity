"""Dự báo PM2.5 theo ngày (Random Forest, v3.7: chỉ PM2.5 quá khứ + lịch), nhiều ngày; yếu tố ảnh hưởng (mô hình ước lượng trong ngày)."""

from core import config  # noqa: F401  (nạp .env và đường dẫn dự án trước)
from database import get_db
from fastapi import Depends
from fastapi import HTTPException
from predict import predict_multiple_days
from predict import predict_next_day
from predict import du_bao_theo_thang
from sqlalchemy import text
from sqlalchemy.orm import Session
import math
from fastapi import APIRouter

router = APIRouter()


@router.get("/api/v1/du-bao-phuong-xa")
def get_forecast_for_ward(lat: float, lon: float, db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT DISTINCT ON (g.tram_id) g.ngay_do, g.no2_mean, g.co_mean, g.so2_mean,
               ST_Y(t.toado) AS lat, ST_X(t.toado) AS lon
        FROM du_lieu_gee_tphcm g
        JOIN tram_quan_trac t ON t.id = g.tram_id
        WHERE t.toado IS NOT NULL
        ORDER BY g.tram_id, g.ngay_do DESC
    """)).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="Chưa có dữ liệu GEE tại các trạm")

    fields = {"no2_mean": "no2_mean", "co_gee": "co_mean", "so2_gee": "so2_mean"}
    local_gee = {}
    latest_dates = []
    for output_field, row_field in fields.items():
        valid = []
        for row in rows:
            value = getattr(row, row_field)
            if value is None:
                continue
            dx = (row.lon - lon) * math.cos(math.radians(lat))
            dy = row.lat - lat
            d2 = dx * dx + dy * dy
            valid.append((d2, float(value), row.ngay_do))
        valid.sort(key=lambda item: item[0])
        valid = valid[:4]
        if valid:
            exact = next((item for item in valid if item[0] < 1e-12), None)
            weights = [1 / max(item[0], 1e-8) for item in valid]
            local_gee[output_field] = exact[1] if exact else sum(item[1] * weight for item, weight in zip(valid, weights)) / sum(weights)
            latest_dates.extend(item[2] for item in valid if item[2])
    if local_gee.get("so2_gee") is not None:
        local_gee["so2_gee"] = max(0.0, local_gee["so2_gee"])

    # Mô hình theo ngày hiện chỉ dùng PM2.5 quá khứ + lịch, nên KHÔNG có thông tin riêng cho từng phường/xã.
    # Trả dự báo cấp thành phố kèm chỉ số vệ tinh tại khu vực chỉ để tham khảo (không đưa vào mô hình).
    forecast = predict_next_day()
    if "error" in forecast:
        return forecast
    return {
        **forecast,
        "gee_no2": local_gee.get("no2_mean"),
        "gee_co": local_gee.get("co_gee"),
        "gee_so2": local_gee.get("so2_gee"),
        "gee_ngay_moi_nhat": str(max(latest_dates)) if latest_dates else None,
        "pham_vi": "toan_thanh_pho",
        "nguon": "Dự báo cấp thành phố (chưa có mô hình theo phường/xã); chỉ số vệ tinh tại khu vực chỉ để tham khảo"
    }


@router.get("/api/v1/du-bao")
def get_forecast():
    return predict_next_day()


@router.get("/api/v1/du-bao-nhieu-ngay")
def get_forecast_multiple(so_ngay: int = 7):
    return predict_multiple_days(so_ngay)


@router.get("/api/v1/du-bao-thang")
def get_forecast_months(so_thang: int = 3):
    """Xu hướng PM2.5 theo mùa cho các tháng tới (khí hậu học + dị thường gần đây), kèm kiểm chứng ngược."""
    return du_bao_theo_thang(max(1, min(int(so_thang), 6)))


@router.get("/api/v1/danh-gia-xac-suat")
def get_danh_gia_xac_suat():
    """Kiểm chứng dự báo xác suất trên các ngày sau mốc huấn luyện (PICP, Brier, bảng độ tin cậy) — ml/danh_gia_xac_suat.py."""
    import json
    from core.config import PROJECT_ROOT
    f = PROJECT_ROOT / "models" / "danh_gia_xac_suat.json"
    if not f.exists():
        raise HTTPException(status_code=404, detail="Chưa chạy: python ml/danh_gia_xac_suat.py")
    return json.loads(f.read_text(encoding="utf-8"))


@router.get("/api/v1/doi-chieu-tram-that")
def get_doi_chieu_tram_that():
    """CAMS so với số đo thật tại trạm mặt đất (OpenAQ: Lãnh sự quán Mỹ, AirGradient) — data_pipeline/tai_tram_that.py."""
    import json
    from core.config import PROJECT_ROOT
    f = PROJECT_ROOT / "models" / "doi_chieu_tram_that.json"
    if not f.exists():
        raise HTTPException(status_code=404, detail="Chưa chạy: python data_pipeline/tai_tram_that.py")
    return json.loads(f.read_text(encoding="utf-8"))


@router.get("/api/v1/mo-hinh-tram-that")
def get_mo_hinh_tram_that():
    """So sánh 5 cách dự báo PM2.5 THẬT ngày mai tại điểm đo CMT8 (ml/mo_hinh_tram_that.py)."""
    import json
    from core.config import PROJECT_ROOT
    f = PROJECT_ROOT / "models" / "mo_hinh_tram_that.json"
    if not f.exists():
        raise HTTPException(status_code=404, detail="Chưa chạy: python ml/mo_hinh_tram_that.py")
    return json.loads(f.read_text(encoding="utf-8"))


@router.get("/api/v1/du-bao-tram-that")
def get_du_bao_tram_that():
    """Dự báo PM2.5 ngày mai từ số đo thật mới nhất (OpenAQ) tại điểm CMT8."""
    from services import du_bao_tram_that
    try:
        return du_bao_tram_that.du_bao()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Chưa có mô hình: python ml/mo_hinh_tram_that.py")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Chưa dự báo được từ số đo thật: {e}")


@router.get("/api/v1/du-bao-da-chat")
def get_du_bao_da_chat():
    """Dự báo ngày mai cho PM2.5, PM10, O₃ (trung bình thành phố) bằng mô hình đã chọn theo kiểm định; kèm kỹ năng."""
    import json
    import joblib
    import pandas as pd
    from core.config import PROJECT_ROOT
    import du_bao_da_chat as ddc
    f, fj = PROJECT_ROOT / "models" / "du_bao_da_chat.joblib", PROJECT_ROOT / "models" / "du_bao_da_chat.json"
    if not f.exists():
        raise HTTPException(status_code=404, detail="Chưa chạy: python ml/du_bao_da_chat.py")
    goi, dg = joblib.load(f), json.loads(fj.read_text(encoding="utf-8"))
    df = ddc.doc_chuoi().set_index("ngay_do").asfreq("D")
    kq = {}
    for ma, (ten, cot) in goi["chat"].items():
        b = ddc.tao_dac_trung(df[cot].interpolate(limit=2)).dropna(subset=goi["dac_trung"])
        if b.empty:
            continue
        x, chon = b[goi["dac_trung"]].iloc[[-1]], goi["chon"][ma]
        p = float(x["y"].iloc[0]) if chon == "Mai = hôm nay" else float(goi["mo_hinh"][ma]["ridge" if chon == "Hồi quy tuyến tính" else "rf"].predict(x)[0])
        m = dg["chat"][ma]["mo_hinh"].get(chon, {})
        kq[ma] = {"ten": ten, "ngay_du_bao": str((b.index[-1] + pd.Timedelta(days=1)).date()), "du_bao": round(p, 1),
                  "hom_nay": round(float(x["y"].iloc[0]), 1), "mo_hinh": chon, "ky_nang": m.get("ky_nang"), "ky_nang_ci95": m.get("ky_nang_ci95")}
    return {"chat": kq, "khong_du_bao": dg["khong_du_bao"], "luu_y": dg["luu_y"]}


@router.get("/api/v1/phan-tich-yeu-to")
def phan_tich_yeu_to():
    """Phân tích các yếu tố ảnh hưởng nhiều nhất đến dự báo PM2.5."""
    import joblib
    model = joblib.load("../models/random_forest_pm25.pkl")
    metadata = joblib.load("../models/model_metadata.pkl")

    ten_de_hieu = {
        'no2_mean': 'Nồng độ NO2', 'co_gee': 'Nồng độ CO', 'so2_gee': 'Nồng độ SO2',
        'o3_mean': 'Nồng độ O3', 'nhiet_do_mean': 'Nhiệt độ', 'do_am_mean': 'Độ ẩm',
        'gio_toc_do_mean': 'Tốc độ gió', 'mua_tong': 'Lượng mưa',
        'thang': 'Tháng trong năm', 'ngay_trong_tuan': 'Ngày trong tuần', 'la_cuoi_tuan': 'Cuối tuần',
        'pm25_lag1': 'PM2.5 hôm qua', 'pm25_lag2': 'PM2.5 2 ngày trước',
        'pm25_lag3': 'PM2.5 3 ngày trước', 'pm25_lag5': 'PM2.5 5 ngày trước', 'pm25_lag7': 'PM2.5 7 ngày trước',
        'no2_lag1': 'NO2 hôm qua', 'no2_lag2': 'NO2 2 ngày trước',
        'gio_lag1': 'Tốc độ gió hôm qua', 'gio_lag2': 'Tốc độ gió 2 ngày trước',
        'pm25_rolling3': 'PM2.5 TB 3 ngày', 'pm25_rolling7': 'PM2.5 TB 7 ngày',
        'pm25_std7': 'Độ biến động PM2.5 (7 ngày)', 'pm25_delta': 'Thay đổi PM2.5 gần đây',
        'gio_rolling3': 'Tốc độ gió TB 3 ngày', 'nhietdo_x_doam': 'Tương tác Nhiệt độ×Độ ẩm'
    }

    importances = model.feature_importances_
    features = metadata['features']

    ket_qua = sorted(
        [{"yeu_to": ten_de_hieu.get(f, f), "muc_do_anh_huong": round(float(imp) * 100, 1)}
         for f, imp in zip(features, importances)],
        key=lambda x: x['muc_do_anh_huong'], reverse=True
    )

    return ket_qua[:8]  # top 8 yếu tố ảnh hưởng nhiều nhất


@router.get("/api/v1/du-bao-aqi")
def get_forecast_aqi():
    """Dự báo AQI dựa trên PM2.5 dự báo."""
    import sys
    sys.path.append("..")
    from tinh_aqi import tinh_aqi_tong_hop, phan_loai_aqi

    ket_qua = predict_next_day()
    if "error" in ket_qua:
        return ket_qua

    aqi, chat = tinh_aqi_tong_hop(pm25=ket_qua['pm25_du_bao'])
    ket_qua['aqi'] = aqi
    ket_qua['chat_gay_o_nhiem'] = chat
    return ket_qua


@router.get("/api/v1/danh-gia-mo-hinh")
def danh_gia_mo_hinh():
    """Số liệu đánh giá các mô hình theo ngày (tập kiểm tra theo thời gian, kiểm chéo cuốn chiếu, CI bootstrap)
    cho trang Phương pháp & Kiểm chứng. Đọc từ models/model_metadata.pkl do ml/train_model.py ghi."""
    from predict import MODEL_DIR
    import joblib
    f = MODEL_DIR / "model_metadata.pkl"
    if not f.exists():
        raise HTTPException(status_code=404, detail="Chưa có models/model_metadata.pkl. Chạy: python ml/train_model.py")
    meta = joblib.load(f)
    giu = ("so_mau", "so_mau_huan_luyen", "so_mau_kiem_tra", "kiem_tra_tu", "so_dac_trung", "nen",
           "random_forest", "hoi_quy_tuyen_tinh", "cay_quyet_dinh", "kiem_cheo_cuon_chieu")

    def sach(x):
        if isinstance(x, dict):
            return {k: sach(v) for k, v in x.items() if k not in ("phan_vi_sai_so", "tham_so")}
        if isinstance(x, (list, tuple)):
            return [sach(v) for v in x]
        if isinstance(x, float):
            return None if math.isnan(x) else round(x, 4)
        return x if isinstance(x, (int, str, bool, type(None))) else str(x)

    return {"huan_luyen_luc": meta.get("trained_at"), "khoang_du_lieu": meta.get("data_range"),
            "mo_hinh": {ten: sach({k: v for k, v in mh.items() if k in giu})
                        for ten, mh in meta.get("danh_gia", {}).get("mo_hinh", {}).items()}}
