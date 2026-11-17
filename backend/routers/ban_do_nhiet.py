"""API bản đồ nhiệt dự báo: GET /api/v1/ban-do-nhiet?so_ngay=3&do_phan_giai=40"""

from core import config  # noqa: F401
from core import logbus
from database import get_db
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from datetime import date
import json
import time

import joblib
import numpy as np
import pandas as pd

from services import ban_do_nhiet as bd
from services import ranh_gioi as rg
from services.aqi import _aqi_helpers

router = APIRouter()
_cache = {}
_TTL = 900


@router.get("/api/v1/ban-do-nhiet")
def ban_do_nhiet(so_ngay: int = 3, do_phan_giai: int = 40, db: Session = Depends(get_db)):
    so_ngay = max(1, min(so_ngay, 5))
    do_phan_giai = max(10, min(do_phan_giai, 80))
    khoa = (so_ngay, do_phan_giai)
    if khoa in _cache and time.time() - _cache[khoa][0] < _TTL:
        return _cache[khoa][1]
    thu_muc = config.PROJECT_ROOT / "models"
    try:
        model = joblib.load(thu_muc / "random_forest_pm25_diem.pkl")
        meta = json.loads((thu_muc / "diem_chi_so.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Chưa huấn luyện mô hình theo điểm. Chạy: python ml/train_diem.py")

    trams = db.execute(text("""SELECT id, to_jsonb(t) AS j, ST_Y(toado::geometry) AS lat, ST_X(toado::geometry) AS lon
                               FROM tram_quan_trac t WHERE toado IS NOT NULL""")).fetchall()
    if len(trams) < 3:
        raise HTTPException(status_code=404, detail="Cần ít nhất 3 trạm có tọa độ để nội suy bản đồ.")
    thong_tin = {int(r.id): {"ma_tram": (r.j or {}).get("ma_tram"), "ten_tram": (r.j or {}).get("ten_tram"),
                             "lat": float(r.lat), "lon": float(r.lon)} for r in trams}
    rows = db.execute(text("""SELECT tram_id, ngay_do, pm25_mean FROM du_lieu_tram_mat_dat
                              WHERE ngay_do >= CURRENT_DATE - 60 AND pm25_mean IS NOT NULL""")).fetchall()
    dai = pd.DataFrame(rows, columns=["tram_id", "ngay_do", "pm25_mean"])
    dai["ngay_do"] = pd.to_datetime(dai["ngay_do"])
    dai = dai[dai["tram_id"].isin(thong_tin)]
    ok, bo, ngay = bd.du_bao_cac_diem(dai, model, meta, so_ngay, date.today())
    if len(ok) < 3:
        raise HTTPException(status_code=422, detail="Không đủ trạm có dữ liệu hợp lệ để dự báo: " + "; ".join(sorted(set(bo.values()))[:2]))

    ids = sorted(ok)
    lat = np.array([thong_tin[i]["lat"] for i in ids]); lon = np.array([thong_tin[i]["lon"] for i in ids])
    co_rg = rg.co_du_lieu()
    phuong = rg.ds_phuong() if co_rg else []
    luoi, glat, glon = bd.tao_luoi(lat, lon, do_phan_giai, khung=rg.khung_ban_do() if co_rg else None)
    f_aqi, _ = _aqi_helpers()
    rmse = meta.get("random_forest", {}).get("RMSE")
    anh, tram_out = [], []
    for k in range(so_ngay):
        v = np.array([ok[i][k] for i in ids])
        pm = bd.noi_suy_idw(lat, lon, v, glat, glon)
        aqi = bd.aqi_luoi(pm, f_aqi)
        chenh, cb = bd.canh_bao_khong_gian(v, rmse)
        tung_phuong, khu_vuc = bd.danh_gia_vung(phuong, lat, lon, v, f_aqi)
        anh.append({"ngay": ngay[k], "da_kiem_chung": k == 0, "pm25": np.round(pm, 1).tolist(),
                    "aqi": [[None if np.isnan(x) else int(x) for x in row] for row in aqi],
                    "chenh_max_min": round(chenh, 2), "canh_bao": cb,
                    "sai_so_noi_suy": bd.sai_so_bo_mot_tram(lat, lon, v), "phuong": tung_phuong, "khu_vuc": khu_vuc})
    for i in ids:
        pm_i = ok[i]
        tram_out.append({"id": i, **thong_tin[i], "pm25": pm_i,
                         "aqi": [(lambda a: None if a != a else int(a))(bd.aqi_luoi(np.array([x]), f_aqi)[0]) for x in pm_i]})
    kq = {"ngay": ngay, "luoi": luoi, "anh": anh,
          "ranh_gioi": {"co": co_rg, "duong_bao": rg.duong_bao_thanh_pho(True) if co_rg else None,
                        "phuong": [{k: p[k] for k in ("ma", "ten_day_du", "khu_vuc", "tram_gan_nhat", "km_tram_gan_nhat", "do_tin_cay")} for p in phuong]},
          "tram": tram_out, "tram_bo_qua": bo, "thang_mau": bd.THANG_MAU,
          "mo_hinh": {"so_tram": meta.get("so_tram"), "kiem_tra_tu": meta.get("kiem_tra_tu"),
                      "ky_nang": meta.get("random_forest", {}).get("ky_nang_so_voi_hom_qua"),
                      "ky_nang_ci95": meta.get("random_forest", {}).get("ky_nang_ci95_bootstrap"),
                      "khong_gian": meta.get("khong_gian")},
          "luu_y": ["Bước 1: dự báo theo thời gian cho từng trạm (Random Forest). Bước 2: nội suy IDW theo không gian cho từng ngày.",
                    "Chỉ ngày đầu được kiểm chứng; các ngày sau suy ra đệ quy, chỉ tham khảo.",
                    "Ranh giới 168 phường/xã và khoảng cách tới trạm gần nhất tính bằng PostGIS (ST_PointOnSurface, KNN <->, ST_Distance).",
                    "Số liệu PM2.5 gốc là đầu ra mô hình CAMS (lưới ~0,4°), không phải đo mặt đất."]}
    _cache[khoa] = (time.time(), kq)
    return kq
