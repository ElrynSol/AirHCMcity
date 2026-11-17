"""API kịch bản: GET /api/v1/kich-ban/mac-dinh và POST /api/v1/kich-ban (xem services/kich_ban.py)."""

from core import config  # noqa: F401
from core import logbus
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict
import time

import joblib
import train_model as tm
from services import kich_ban as kb
from services.aqi import _aqi_helpers
from tinh_aqi import muc_aqi, tinh_aqi_tong_hop

router = APIRouter()
_cache = {"t": 0, "v": None}
_TTL = 3600


class YeuCauKichBan(BaseModel):
    thay_doi: Dict[str, float] = {}


def _nap():
    if _cache["v"] and time.time() - _cache["t"] < _TTL:
        return _cache["v"]
    thu_muc = config.PROJECT_ROOT / "models"
    try:
        rf = joblib.load(thu_muc / "random_forest_pm25.pkl")
        tt = joblib.load(thu_muc / "linear_pm25.pkl")
        meta = joblib.load(thu_muc / "model_metadata.pkl")
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Chưa có mô hình kịch bản. Chạy: python ml/train_model.py")
    khoang = meta.get("khoang_dac_trung")
    if not khoang:
        raise HTTPException(status_code=503, detail="Mô hình cũ chưa có khoảng huấn luyện. Chạy lại: python ml/train_model.py")
    try:
        df = tm.tao_dac_trung(tm.doc_tu_csdl())
    except Exception as exc:
        logbus.ghi("ERROR", "kich_ban", "doc_csdl_that_bai", f"{type(exc).__name__}: {exc}")
        raise HTTPException(status_code=500, detail="Không đọc được dữ liệu nền từ CSDL.")
    features = meta["features"]
    hang, ngay = kb.tao_hang_nen(df, features)
    if hang is None:
        raise HTTPException(status_code=503, detail="Không có ngày nào đủ dữ liệu để làm nền kịch bản.")
    v = {"mo_hinh": {"random_forest": rf, "tuyen_tinh": tt}, "features": features, "hang": hang, "ngay": ngay,
         "khoang": khoang, "meta": meta}
    _cache.update({"t": time.time(), "v": v})
    return v


def _them_aqi(kq):
    try:
        f, _ = _aqi_helpers()
        for nhom in ("nen", "kich_ban"):
            kq[nhom + "_aqi"] = {k: f(pm25=v)[0] for k, v in kq[nhom].items()}
    except Exception:
        pass
    return kq


@router.get("/api/v1/kich-ban/mac-dinh")
def mac_dinh():
    n = _nap()
    kq = kb.chay_kich_ban(n["mo_hinh"], n["features"], n["hang"], n["khoang"], {})
    dm = n["meta"].get("danh_gia", {}).get("mo_hinh", {}).get("uoc_luong_trong_ngay", {})
    return {"ngay_nen": str(n["ngay"].date()), "bien": kb.thong_tin_bien(n["hang"], n["khoang"]),
            "duong_nhay": kb.duong_nhay(n["mo_hinh"], n["features"], n["hang"], n["khoang"]),
            "du_doan_nen": _them_aqi(kq), "danh_gia_nen": kb.danh_gia(kq, dm, muc_aqi, tinh_aqi_tong_hop),
            "kich_ban_mau": [{"ma": k, "ten": v["ten"], "mo_ta": v["mo_ta"], "thay_doi": kb.thay_doi_mau(k, n["khoang"])} for k, v in kb.KICH_BAN_MAU.items()],
            "mo_hinh_chi_so": {k: {m: (dm.get(k) or {}).get(m) for m in ("RMSE", "MAE", "R2")} for k in ("random_forest", "hoi_quy_tuyen_tinh")},
            "ky_nang_mo_hinh": {"random_forest": (dm.get("random_forest") or {}).get("ky_nang_so_voi_hom_qua"),
                                "tuyen_tinh": (dm.get("hoi_quy_tuyen_tinh") or {}).get("ky_nang_so_voi_hom_qua")},
            "ghi_chu": kb.GHI_CHU}


def _chi_so(n):
    return n["meta"].get("danh_gia", {}).get("mo_hinh", {}).get("uoc_luong_trong_ngay", {})


@router.post("/api/v1/kich-ban")
def chay(yc: YeuCauKichBan):
    n = _nap()
    try:
        kq = kb.chay_kich_ban(n["mo_hinh"], n["features"], n["hang"], n["khoang"], yc.thay_doi)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    kq["ngay_nen"] = str(n["ngay"].date())
    kq["ghi_chu"] = kb.GHI_CHU
    kq["danh_gia"] = kb.danh_gia(kq, _chi_so(n), muc_aqi, tinh_aqi_tong_hop)
    return _them_aqi(kq)


@router.get("/api/v1/kich-ban/so-sanh")
def so_sanh():
    """Chạy toàn bộ kịch bản mẫu trên cùng ngày nền để so sánh cạnh nhau."""
    n = _nap()
    ds = []
    for ma, kbm in kb.KICH_BAN_MAU.items():
        kq = kb.chay_kich_ban(n["mo_hinh"], n["features"], n["hang"], n["khoang"], kb.thay_doi_mau(ma, n["khoang"]))
        dg = kb.danh_gia(kq, _chi_so(n), muc_aqi, tinh_aqi_tong_hop)
        ds.append({"ma": ma, "ten": kbm["ten"], "mo_ta": kbm["mo_ta"], "random_forest": kq["kich_ban"]["random_forest"],
                   "tuyen_tinh": kq["kich_ban"]["tuyen_tinh"], "hai_mo_hinh_trai_chieu": kq["hai_mo_hinh_trai_chieu"],
                   **{k: dg[k] for k in ("pm25_nen", "pm25_kich_ban", "chenh_lech", "phan_tram", "aqi_kich_ban", "muc_kich_ban")},
                   "tin_cay": dg["tin_cay"]["muc"], "khoang_80": dg["tin_cay"]["khoang_80"]})
    return {"ngay_nen": str(n["ngay"].date()), "kich_ban": ds,
            "thay_doi_mau": {ma: kb.thay_doi_mau(ma, n["khoang"]) for ma in kb.KICH_BAN_MAU}}
