"""Thống kê AQI và trạng thái nguồn dữ liệu."""

from core import config  # noqa: F401  (nạp .env và đường dẫn dự án trước)
from core.nguong import qcvn_pm25_24h
from database import get_db
from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi import APIRouter
from services.aqi import _aqi_helpers

router = APIRouter()


@router.get("/api/v1/thong-ke")
def thong_ke(so_ngay: int = 90, tram_id: int = None, db: Session = Depends(get_db)):
    """Thống kê AQI theo ngày/tháng cho toàn TP (trung bình các trạm) hoặc 1 trạm."""
    tinh_aqi_tong_hop, phan_loai_aqi = _aqi_helpers()
    so_ngay = max(7, min(int(so_ngay), 730))
    dieu_kien = "AND tram_id = :tid" if tram_id else ""
    params = {"n": so_ngay}
    if tram_id:
        params["tid"] = tram_id
    rows = db.execute(text(f"""
        SELECT ngay_do,
               AVG(COALESCE(pm25_smoothed, pm25_mean)) AS pm25,
               AVG(COALESCE(pm10_smoothed, pm10_mean)) AS pm10,
               AVG(COALESCE(o3_smoothed, o3_mean)) AS o3
        FROM du_lieu_tram_mat_dat
        WHERE ngay_do IS NOT NULL {dieu_kien}
        GROUP BY ngay_do ORDER BY ngay_do DESC LIMIT :n
    """), params).fetchall()
    if not rows:
        return {"error": "Chưa có dữ liệu"}

    ngay = []
    for r in reversed(rows):
        aqi, chat = tinh_aqi_tong_hop(pm25=r.pm25, pm10=r.pm10, o3=r.o3)
        ngay.append({"ngay": str(r.ngay_do), "pm25": None if r.pm25 is None else round(float(r.pm25), 1),
                     "pm10": None if r.pm10 is None else round(float(r.pm10), 1),
                     "aqi": aqi, "muc_do": phan_loai_aqi(aqi) if aqi is not None else None})

    phan_bo = {}
    for d in ngay:
        if d["muc_do"]:
            phan_bo[d["muc_do"]] = phan_bo.get(d["muc_do"], 0) + 1

    thang = {}
    for d in ngay:
        k = d["ngay"][:7]
        t = thang.setdefault(k, {"thang": k, "pm25": [], "aqi_max": 0, "so_ngay": 0})
        if d["pm25"] is not None:
            t["pm25"].append(d["pm25"])
        if d["aqi"] is not None:
            t["aqi_max"] = max(t["aqi_max"], d["aqi"])
        t["so_ngay"] += 1
    theo_thang = [{"thang": t["thang"], "pm25_tb": round(sum(t["pm25"]) / len(t["pm25"]), 1) if t["pm25"] else None,
                   "aqi_max": t["aqi_max"], "so_ngay": t["so_ngay"]} for t in thang.values()]

    pm25_vals = [d["pm25"] for d in ngay if d["pm25"] is not None]
    aqi_vals = [d for d in ngay if d["aqi"] is not None]
    xau_nhat = max(aqi_vals, key=lambda d: d["aqi"]) if aqi_vals else None

    # Xếp hạng trạm trong cùng kỳ
    theo_tram = []
    if not tram_id:
        xep = db.execute(text("""
            SELECT t.id, t.ma_tram, t.ten_tram,
                   AVG(COALESCE(m.pm25_smoothed, m.pm25_mean)) AS pm25_tb,
                   SUM(CASE WHEN COALESCE(m.pm25_smoothed, m.pm25_mean) > (CASE WHEN m.ngay_do >= DATE '2026-01-01' THEN 45 ELSE 50 END) THEN 1 ELSE 0 END) AS ngay_vuot,
                   COUNT(*) AS so_ngay
            FROM (SELECT * FROM du_lieu_tram_mat_dat WHERE ngay_do >= (SELECT MAX(ngay_do) FROM du_lieu_tram_mat_dat) - (:n || ' days')::interval) m
            JOIN tram_quan_trac t ON t.id = m.tram_id
            GROUP BY t.id, t.ma_tram, t.ten_tram ORDER BY pm25_tb DESC NULLS LAST
        """), {"n": str(so_ngay)}).fetchall()
        theo_tram = [{"tram_id": x.id, "ma_tram": x.ma_tram, "ten_tram": x.ten_tram,
                      "pm25_tb": None if x.pm25_tb is None else round(float(x.pm25_tb), 1),
                      "ngay_vuot_pm25": int(x.ngay_vuot or 0), "so_ngay": int(x.so_ngay)} for x in xep]

    return {
        "tu_ngay": ngay[0]["ngay"], "den_ngay": ngay[-1]["ngay"], "so_ngay": len(ngay),
        "pm25_tb": round(sum(pm25_vals) / len(pm25_vals), 1) if pm25_vals else None,
        "pm25_max": max(pm25_vals) if pm25_vals else None,
        "pm25_min": min(pm25_vals) if pm25_vals else None,
        # Ngưỡng PM2.5 TB 24 giờ QCVN 05:2023/BTNMT theo từng ngày: 50 µg/Nm³ đến hết 2025, 45 từ 01/01/2026
        "ngay_vuot_pm25_qcvn": sum(1 for d in ngay if d["pm25"] is not None and d["pm25"] > qcvn_pm25_24h(d["ngay"])),
        "nguong_qcvn_hien_hanh": qcvn_pm25_24h(),
        "ngay_xau_nhat": xau_nhat,
        "phan_bo_muc_do": phan_bo, "theo_ngay": ngay, "theo_thang": theo_thang, "theo_tram": theo_tram,
        "luu_y": "Giá trị PM2.5/PM10/O3 là số liệu mô hình (Open-Meteo), đã hiệu chỉnh không gian, chưa kiểm chứng đo đạc mặt đất."
    }


@router.get("/api/v1/trang-thai-du-lieu")
def trang_thai_du_lieu(db: Session = Depends(get_db)):
    """Tình trạng từng nguồn dữ liệu: số dòng, khoảng ngày, độ trễ, độ phủ trạm, mức trùng lặp giá trị."""
    from datetime import date

    def tom_tat(bang, cot_kiem):
        r = db.execute(text(f"""
            SELECT COUNT(*) AS n, COUNT(DISTINCT tram_id) AS so_tram, MIN(ngay_do) AS tu, MAX(ngay_do) AS den,
                   COUNT({cot_kiem}) AS co_gia_tri
            FROM {bang}
        """)).fetchone()
        tung_tram = db.execute(text(f"""
            SELECT t.ma_tram, t.ten_tram, COUNT(m.*) AS n, MAX(m.ngay_do) AS den
            FROM tram_quan_trac t LEFT JOIN {bang} m ON m.tram_id = t.id
            GROUP BY t.ma_tram, t.ten_tram ORDER BY t.ma_tram
        """)).fetchall()
        hom_nay = date.today()
        return {
            "so_dong": int(r.n or 0), "so_tram": int(r.so_tram or 0),
            "tu_ngay": str(r.tu) if r.tu else None, "den_ngay": str(r.den) if r.den else None,
            "tre_ngay": (hom_nay - r.den).days if r.den else None,
            "ty_le_co_gia_tri": round(100 * (r.co_gia_tri or 0) / r.n, 1) if r.n else None,
            "tung_tram": [{"ma_tram": x.ma_tram, "ten_tram": x.ten_tram, "so_dong": int(x.n or 0),
                           "den_ngay": str(x.den) if x.den else None,
                           "tre_ngay": (hom_nay - x.den).days if x.den else None} for x in tung_tram],
        }

    ket_qua = {"ngay_kiem_tra": date.today().isoformat()}
    ket_qua["mat_dat"] = tom_tat("du_lieu_tram_mat_dat", "pm25_mean")
    ket_qua["ve_tinh"] = tom_tat("du_lieu_gee_tphcm", "no2_mean")

    # Mức hiệu chỉnh và trùng lặp giá trị thô giữa các trạm (cùng ô lưới ~45 km)
    try:
        r = db.execute(text("""
            SELECT COUNT(*) AS n, COUNT(pm25_smoothed) AS n_min,
                   (SELECT COUNT(DISTINCT pm25_mean) FROM du_lieu_tram_mat_dat WHERE ngay_do = (SELECT MAX(ngay_do) FROM du_lieu_tram_mat_dat)) AS gia_tri_khac_nhau,
                   (SELECT COUNT(*) FROM du_lieu_tram_mat_dat WHERE ngay_do = (SELECT MAX(ngay_do) FROM du_lieu_tram_mat_dat)) AS tram_ngay_moi
            FROM du_lieu_tram_mat_dat
        """)).fetchone()
        ket_qua["hieu_chinh"] = {
            "so_dong_da_hieu_chinh": int(r.n_min or 0), "tong_dong": int(r.n or 0),
            "ngay_moi_nhat_so_tram": int(r.tram_ngay_moi or 0),
            "ngay_moi_nhat_so_gia_tri_pm25_khac_nhau": int(r.gia_tri_khac_nhau or 0),
        }
    except Exception as exc:
        db.rollback()
        ket_qua["hieu_chinh"] = {"loi": str(exc)}

    # Thông tin mô hình dự báo (nếu đọc được)
    try:
        import joblib
        md = joblib.load("../models/model_metadata.pkl")
        ket_qua["mo_hinh"] = {k: v for k, v in md.items() if isinstance(v, (int, float, str))}
        if "features" in md:
            ket_qua["mo_hinh"]["so_dac_trung"] = len(md["features"])
    except Exception as exc:
        ket_qua["mo_hinh"] = {"loi": f"Không đọc được metadata mô hình ({type(exc).__name__})"}
    return ket_qua
