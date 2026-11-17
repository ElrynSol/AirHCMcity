"""Bản đồ nhiệt PM2.5 dự báo: (1) dự báo theo thời gian cho từng trạm → (2) nội suy không gian cho từng mốc thời gian (v3.9).

Nội suy IDW (nghịch đảo khoảng cách). Độ tin cậy nội suy đo bằng "bỏ một trạm" (leave-one-station-out): bỏ từng trạm,
nội suy lại từ các trạm còn lại, so với giá trị của trạm bị bỏ; đối chiếu với nền "lấy trung bình các trạm còn lại".
"""

import numpy as np
import pandas as pd

import predict as pr

# Thang màu AQI Việt Nam (QĐ 1459/QĐ-TCMT) — lấy từ nguồn chung tinh_aqi.THANG_AQI
from tinh_aqi import THANG_AQI  # noqa: E402

THANG_MAU = [{"tu": m["tu"], "den": m["den"], "muc": m["muc"], "mau": m["mau"]} for m in THANG_AQI]


def du_bao_cac_diem(dai, model, meta_diem, so_ngay, hom_nay):
    """dai: cột tram_id, ngay_do, pm25_mean (≈60 ngày gần nhất). Trả ({tram_id: [pm25 theo ngày]}, {tram_id: lý do bỏ}, ngày)."""
    meta = {"features_du_bao_ngay_mai": __import__("train_model").FEATURES_DU_BAO,
            "du_bao_metrics": {"phan_vi_sai_so": (meta_diem or {}).get("random_forest", {}).get("phan_vi_sai_so")}}
    ok, bo, ngay = {}, {}, None
    for tid, g in dai.groupby("tram_id"):
        r = pr.du_bao_tu_chuoi(g[["ngay_do", "pm25_mean"]], model, meta, so_ngay, hom_nay)
        if isinstance(r, dict):
            bo[int(tid)] = r["error"]
            continue
        kq, _ = r
        ok[int(tid)] = [x["pm25"] for x in kq]
        ngay = [x["ngay"] for x in kq]
    return ok, bo, ngay


def _kc2(lat, lon, glat, glon):
    dx = (np.asarray(glon)[..., None] - lon) * np.cos(np.radians(10.8))
    dy = np.asarray(glat)[..., None] - lat
    return dx * dx + dy * dy


def noi_suy_idw(lat, lon, val, glat, glon, p=2.0):
    """lat/lon/val: mảng trạm; glat/glon: mảng điểm cần nội suy (cùng hình dạng). Trả mảng cùng hình dạng glat."""
    lat, lon, val = (np.asarray(x, float) for x in (lat, lon, val))
    d2 = _kc2(lat, lon, glat, glon)
    w = 1.0 / np.maximum(d2, 1e-10) ** (p / 2)
    return (w * val).sum(-1) / w.sum(-1)


def sai_so_bo_mot_tram(lat, lon, val, p=2.0):
    lat, lon, val = (np.asarray(x, float) for x in (lat, lon, val))
    n = len(val)
    if n < 3:
        return None
    du, nen = [], []
    for i in range(n):
        m = np.arange(n) != i
        du.append(float(noi_suy_idw(lat[m], lon[m], val[m], np.array(lat[i]), np.array(lon[i]), p)))
        nen.append(float(val[m].mean()))
    du, nen = np.array(du), np.array(nen)
    rmse = float(np.sqrt(np.mean((du - val) ** 2)))
    rmse_nen = float(np.sqrt(np.mean((nen - val) ** 2)))
    return {"RMSE_idw": rmse, "MAE_idw": float(np.mean(np.abs(du - val))), "RMSE_trung_binh_cac_tram_con_lai": rmse_nen,
            "ky_nang_so_voi_trung_binh": (1 - rmse / rmse_nen) if rmse_nen > 1e-9 else None, "so_tram": n}


def danh_gia_vung(phuong, lat, lon, v, f_aqi):
    """Nội suy PM2.5 tại điểm đại diện của từng phường (ST_PointOnSurface) rồi tổng hợp theo khu vực.
    phuong: danh sách từ services.ranh_gioi.ds_phuong(). Trả (giá trị từng phường, tóm tắt theo khu vực)."""
    if not phuong:
        return [], []
    plat = np.array([p["lat"] for p in phuong]); plon = np.array([p["lon"] for p in phuong])
    pm = noi_suy_idw(lat, lon, v, plat, plon)
    aqi = aqi_luoi(pm, f_aqi)
    tung = [{"ma": p["ma"], "pm25": round(float(x), 1), "aqi": None if np.isnan(a) else int(a)} for p, x, a in zip(phuong, pm, aqi)]
    khu = {}
    for p, t in zip(phuong, tung):
        khu.setdefault(p["khu_vuc"], []).append((t, p))
    tom = []
    for ten, ds_tat_ca in sorted(khu.items()):
        # Xếp hạng chỉ dùng phường cách trạm ≤ 15 km: giá trị nơi xa trạm là ngoại suy, không đủ tin để gọi "cao nhất/thấp nhất"
        ds = [x for x in ds_tat_ca if x[1]["do_tin_cay"] != "thap"] or ds_tat_ca
        gt = np.array([t["pm25"] for t, _ in ds])
        cao = max(ds, key=lambda x: x[0]["pm25"]); thap = min(ds, key=lambda x: x[0]["pm25"])
        tom.append({"khu_vuc": ten, "so_phuong": len(ds_tat_ca), "so_phuong_xep_hang": len(ds), "pm25_tb": round(float(gt.mean()), 1),
                    "pm25_cao_nhat": cao[0]["pm25"], "phuong_cao_nhat": cao[1]["ten_day_du"],
                    "pm25_thap_nhat": thap[0]["pm25"], "phuong_thap_nhat": thap[1]["ten_day_du"],
                    "aqi_tb": None if np.isnan(a := aqi_luoi(np.array([gt.mean()]), f_aqi)[0]) else int(a),
                    "so_phuong_tin_cay_thap": sum(1 for _, p in ds_tat_ca if p["do_tin_cay"] == "thap")})
    return tung, tom


def tao_luoi(lat, lon, n=40, le=0.06, khung=None):
    if khung:   # khung đất liền TP.HCM lấy từ PostGIS (services.ranh_gioi.khung_ban_do)
        lat0, lat1, lon0, lon1 = khung["lat0"], khung["lat1"], khung["lon0"], khung["lon1"]
        glat, glon = np.meshgrid(np.linspace(lat1, lat0, n), np.linspace(lon0, lon1, n), indexing="ij")
        return {"lat0": lat0, "lat1": lat1, "lon0": lon0, "lon1": lon1, "n": n}, glat, glon
    lat0, lat1 = float(np.min(lat)) - le, float(np.max(lat)) + le
    lon0, lon1 = float(np.min(lon)) - le, float(np.max(lon)) + le
    glat, glon = np.meshgrid(np.linspace(lat1, lat0, n), np.linspace(lon0, lon1, n), indexing="ij")  # hàng 0 = phía bắc
    return {"lat0": lat0, "lat1": lat1, "lon0": lon0, "lon1": lon1, "n": n}, glat, glon


def canh_bao_khong_gian(gia_tri_cac_tram, rmse_mo_hinh):
    """Cảnh báo nếu chênh lệch giữa các trạm nhỏ hơn sai số dự báo: khi đó cấu trúc không gian không đáng diễn giải."""
    v = np.asarray(gia_tri_cac_tram, float)
    chenh = float(v.max() - v.min()) if len(v) else 0.0
    cb = []
    if chenh < max(rmse_mo_hinh or 0, 2.0):
        cb.append(f"Chênh lệch dự báo lớn nhất giữa các trạm chỉ {chenh:.1f} µg/m³, nhỏ hơn sai số dự báo (RMSE ≈ {rmse_mo_hinh or 0:.1f}). "
                  "Bản đồ gần như đồng màu: không nên diễn giải sự khác biệt giữa các khu vực.")
    return chenh, cb


def aqi_luoi(pm, tinh_aqi):
    """pm: mảng PM2.5; tinh_aqi(pm25=x) -> (aqi, chất). Gộp theo giá trị làm tròn 0,1 để gọi hàm ít lần."""
    r = np.round(pm, 1)
    cache = {}
    out = np.empty(r.shape, dtype=float)
    for idx, x in np.ndenumerate(r):
        x = float(x)
        if x not in cache:
            try:
                cache[x] = float(tinh_aqi(pm25=x)[0])
            except Exception:
                cache[x] = float("nan")
        out[idx] = cache[x]
    return out
