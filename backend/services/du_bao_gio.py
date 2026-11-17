"""Dự báo PM2.5 THEO GIỜ cho 1–24 giờ tới (trung tâm TP.HCM).

Phương pháp (viết riêng cho đồ án, đánh giá trung thực):
  - Dữ liệu: chuỗi giờ PM2.5/PM10 (CAMS qua Open-Meteo) và thời tiết (nhiệt độ, độ ẩm, gió, mưa, áp suất).
    Đây là số liệu MÔ HÌNH, không phải đo đạc mặt đất. Lưới CAMS toàn cầu ~0,4° nên dùng 1 điểm đại diện cho thành phố.
  - Mô hình "trực tiếp": 1 mô hình HistGradientBoosting cho mọi bước h = 1..24; đặc trưng gồm h, giờ-trong-ngày của thời điểm
    đích và các đặc trưng CHỈ dùng thông tin đến thời điểm t (không nhìn tương lai). Mục tiêu là chênh lệch so với PM2.5 hiện tại.
  - Đánh giá: chia theo THỨ TỰ THỜI GIAN (kiểm tra = 20% cuối, cách tập huấn luyện 24 giờ để không rò rỉ) + kiểm tra chéo
    mở rộng theo thời gian. LUÔN so với 2 mô hình nền: "giữ nguyên giờ hiện tại" (persistence) và "giống hôm qua cùng giờ".
    Chỉ số kỹ năng (skill) = 1 − RMSE_mô_hình / RMSE_persistence; <= 0 nghĩa là mô hình không hơn nền.
  - Khoảng dự báo 80% lấy từ phân vị 10%/90% của sai số THỰC trên tập kiểm tra theo từng bước h.
Không dùng PM2.5 của chính thời điểm đích hay biến nào tại t+h làm đầu vào.
"""

from core import config  # noqa: F401
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

BUOC = list(range(1, 25))
THU_MUC_MO_HINH = config.PROJECT_ROOT / "models"
FILE_MO_HINH = THU_MUC_MO_HINH / "du_bao_gio.joblib"
FILE_CHI_SO = THU_MUC_MO_HINH / "du_bao_gio_chi_so.json"
CAC_COT = ["time", "pm2_5", "pm10", "temperature_2m", "relative_humidity_2m", "wind_speed_10m", "precipitation", "surface_pressure"]
DAC_TRUNG = [
    "pm25_t", "pm25_lag1", "pm25_lag2", "pm25_lag3", "pm25_lag6", "pm25_lag12", "pm25_lag24", "pm25_lag48",
    "pm25_tb6", "pm25_tb24", "pm25_tb72", "pm25_std24", "pm25_dao_ham3",
    "pm10_t", "nhiet_do", "do_am", "gio_10m", "mua_6h", "ap_suat",
    "gio_sin", "gio_cos", "ngay_sin", "ngay_cos",
    "buoc", "dich_sin", "dich_cos",
]


def tao_dac_trung(df: pd.DataFrame) -> pd.DataFrame:
    """Đặc trưng tại từng thời điểm t, chỉ dùng thông tin ≤ t. df cần các cột CAC_COT, đã sắp theo giờ liên tục."""
    d = df.copy()
    d["time"] = pd.to_datetime(d["time"])
    d = d.sort_values("time").drop_duplicates("time").set_index("time")
    d = d.asfreq("h")  # chèn giờ thiếu thành NaN để các độ trễ đúng nghĩa
    p = d["pm2_5"]
    f = pd.DataFrame(index=d.index)
    f["pm25_t"] = p
    for k in (1, 2, 3, 6, 12, 24, 48):
        f[f"pm25_lag{k}"] = p.shift(k)
    f["pm25_tb6"] = p.rolling(6, min_periods=4).mean()
    f["pm25_tb24"] = p.rolling(24, min_periods=18).mean()
    f["pm25_tb72"] = p.rolling(72, min_periods=54).mean()
    f["pm25_std24"] = p.rolling(24, min_periods=18).std()
    f["pm25_dao_ham3"] = p - p.shift(3)
    f["pm10_t"] = d["pm10"]
    f["nhiet_do"] = d["temperature_2m"]
    f["do_am"] = d["relative_humidity_2m"]
    f["gio_10m"] = d["wind_speed_10m"]
    f["mua_6h"] = d["precipitation"].rolling(6, min_periods=1).sum()
    f["ap_suat"] = d["surface_pressure"]
    h = f.index.hour
    doy = f.index.dayofyear
    f["gio_sin"] = np.sin(2 * np.pi * h / 24)
    f["gio_cos"] = np.cos(2 * np.pi * h / 24)
    f["ngay_sin"] = np.sin(2 * np.pi * doy / 365.25)
    f["ngay_cos"] = np.cos(2 * np.pi * doy / 365.25)
    return f


def _them_buoc(f: pd.DataFrame, h: int) -> pd.DataFrame:
    x = f.copy()
    gio_dich = (x.index.hour + h) % 24
    x["buoc"] = h
    x["dich_sin"] = np.sin(2 * np.pi * gio_dich / 24)
    x["dich_cos"] = np.cos(2 * np.pi * gio_dich / 24)
    return x[DAC_TRUNG]


def tao_tap_huan_luyen(df: pd.DataFrame, buoc=BUOC):
    """Trả (X, y_chenh_lech, pm25_hien_tai, pm25_that, thoi_diem_t, h). Mỗi hàng là một cặp (t, h)."""
    f = tao_dac_trung(df)
    p = f["pm25_t"]
    cac = []
    for h in buoc:
        x = _them_buoc(f, h)
        y = p.shift(-h)
        x = x.assign(_y=y.values, _t=f.index, _h=h)
        cac.append(x)
    al = pd.concat(cac)
    al = al.dropna(subset=["_y"] + DAC_TRUNG)
    X = al[DAC_TRUNG]
    return X, (al["_y"] - al["pm25_t"]).values, al["pm25_t"].values, al["_y"].values, al["_t"].values, al["_h"].values


def _tao_mo_hinh():
    from sklearn.ensemble import HistGradientBoostingRegressor
    return HistGradientBoostingRegressor(max_iter=250, learning_rate=0.06, max_depth=7, min_samples_leaf=40,
                                         l2_regularization=1.0, random_state=42)


def _r2(y, yh):
    ss = float(np.sum((y - y.mean()) ** 2))
    return float(1 - np.sum((y - yh) ** 2) / ss) if ss > 0 else float("nan")


def _chi_so(y, yh):
    return {"rmse": float(np.sqrt(np.mean((y - yh) ** 2))), "mae": float(np.mean(np.abs(y - yh))), "r2": _r2(y, yh)}


def danh_gia_va_huan_luyen(df: pd.DataFrame, luu: bool = True) -> dict:
    """Đánh giá trung thực rồi huấn luyện lại trên toàn bộ dữ liệu. Trả dict chỉ số (cũng ghi ra JSON nếu luu=True)."""
    X, yd, p0, yt, tt, hh = tao_tap_huan_luyen(df)
    if len(X) < 2000:
        raise ValueError(f"Quá ít mẫu để huấn luyện ({len(X)}). Cần ít nhất vài tháng dữ liệu theo giờ.")
    tt = pd.to_datetime(tt)
    gioi_han = tt.min() + (tt.max() - tt.min()) * 0.8
    moc_val = tt.min() + (tt.max() - tt.min()) * 0.64
    tr = tt <= moc_val - pd.Timedelta(hours=24)           # cách 24 giờ: nhãn của tập huấn luyện không chồng sang tập sau
    va = (tt > moc_val) & (tt <= gioi_han - pd.Timedelta(hours=24))
    te = tt > gioi_han
    mo_hinh = _tao_mo_hinh().fit(X[tr], yd[tr])
    # Hệ số co alpha_h theo từng bước, chọn trên tập VALIDATION (không dùng tập kiểm tra): dự báo = hiện tại + alpha*chênh lệch.
    # alpha ~ 0 nghĩa là ở bước đó mô hình không hơn "giữ nguyên" nên tự lùi về persistence (không tự nhận kỹ năng không có).
    d_va = mo_hinh.predict(X[va])
    alpha = {}
    for h in BUOC:
        m = hh[va] == h
        if m.sum() < 50:
            alpha[h] = 1.0
            continue
        luoi = np.arange(0.0, 1.21, 0.1)
        loi = [np.sqrt(np.mean((yt[va][m] - np.clip(p0[va][m] + a_ * d_va[m], 0, None)) ** 2)) for a_ in luoi]
        alpha[h] = float(luoi[int(np.argmin(loi))])
    a_te = np.array([alpha.get(int(h_), 1.0) for h_ in hh[te]])
    du_doan = np.clip(p0[te] + a_te * mo_hinh.predict(X[te]), 0, None)
    y_te, p_te, h_te = yt[te], p0[te], hh[te]
    lag24 = X["pm25_lag24"].values[te]
    # nền 2: PM2.5 cùng giờ của đích ở ngày trước = giá trị tại t+h-24 (đã biết nếu h<=24): dùng lag tương ứng
    theo_buoc = {}
    cac_buoc_bao = [1, 3, 6, 12, 24]
    sai_so = {}
    for h in BUOC:
        m = h_te == h
        if m.sum() < 50:
            continue
        e = y_te[m] - du_doan[m]
        sai_so[h] = (float(np.quantile(e, 0.10)), float(np.quantile(e, 0.90)))
        ms = _chi_so(y_te[m], du_doan[m])
        mp = _chi_so(y_te[m], p_te[m])
        ms["rmse_persistence"] = mp["rmse"]
        ms["r2_persistence"] = mp["r2"]
        ms["ky_nang_so_voi_persistence"] = float(1 - ms["rmse"] / mp["rmse"]) if mp["rmse"] > 0 else float("nan")
        theo_buoc[h] = ms
    # nền "hôm qua cùng giờ": cần giá trị ở t+h-24; tính bằng cách tra lại chuỗi
    f = tao_dac_trung(df)
    serie = f["pm25_t"]
    cung_gio_hom_qua = serie.reindex(pd.to_datetime(tt[te]) + pd.to_timedelta(h_te - 24, unit="h")).values
    ok = ~np.isnan(cung_gio_hom_qua)
    tong = _chi_so(y_te, du_doan)
    tong["rmse_persistence"] = _chi_so(y_te, p_te)["rmse"]
    tong["rmse_hom_qua_cung_gio"] = _chi_so(y_te[ok], cung_gio_hom_qua[ok])["rmse"] if ok.any() else None
    tong["ky_nang_so_voi_persistence"] = float(1 - tong["rmse"] / tong["rmse_persistence"])

    # kiểm tra chéo mở rộng theo thời gian (3 lần) cho độ ổn định
    cv = []
    moc = [0.5, 0.65, 0.8]
    for a, b in zip(moc, [0.65, 0.8, 1.0]):
        t0 = tt.min() + (tt.max() - tt.min()) * a
        t1 = tt.min() + (tt.max() - tt.min()) * b
        a_tr = tt <= t0 - pd.Timedelta(hours=24)
        a_te = (tt > t0) & (tt <= t1)
        if a_tr.sum() < 1000 or a_te.sum() < 500:
            continue
        mh = _tao_mo_hinh().fit(X[a_tr], yd[a_tr])
        yh = np.clip(p0[a_te] + np.array([alpha.get(int(h_), 1.0) for h_ in hh[a_te]]) * mh.predict(X[a_te]), 0, None)
        c = _chi_so(yt[a_te], yh)
        c["ky_nang_so_voi_persistence"] = float(1 - c["rmse"] / _chi_so(yt[a_te], p0[a_te])["rmse"])
        cv.append(c)

    # huấn luyện lại trên toàn bộ dữ liệu cho bản dùng thật
    cuoi = _tao_mo_hinh().fit(X, yd)
    ket_qua = {
        "so_mau": int(len(X)), "tu": str(tt.min()), "den": str(tt.max()),
        "kiem_tra_tu": str(gioi_han), "tong": tong, "theo_buoc": {str(k): v for k, v in theo_buoc.items() if k in cac_buoc_bao},
        "theo_buoc_day_du": {str(k): v for k, v in theo_buoc.items()},
        "kiem_tra_cheo": cv,
        "phan_vi_sai_so": {str(k): v for k, v in sai_so.items()}, "he_so_co_alpha": {str(k): v for k, v in alpha.items()},
        "luu_y": ("Số liệu gốc là PM2.5/PM10 của mô hình CAMS (Open-Meteo), không phải đo đạc mặt đất. R² cao một phần vì PM2.5 giờ liền kề "
                  "tự tương quan mạnh; hãy đọc cùng 'kỹ năng so với persistence' (mô hình thật sự hơn 'giữ nguyên' bao nhiêu)."),
    }
    if luu:
        import joblib
        THU_MUC_MO_HINH.mkdir(parents=True, exist_ok=True)
        joblib.dump({"mo_hinh": cuoi, "dac_trung": DAC_TRUNG, "phan_vi_sai_so": ket_qua["phan_vi_sai_so"], "alpha": alpha}, FILE_MO_HINH)
        FILE_CHI_SO.write_text(json.dumps(ket_qua, ensure_ascii=False, indent=2), encoding="utf-8")
    return ket_qua


_cache_mo_hinh = {"mtime": None, "obj": None}


def tai_mo_hinh():
    """Nạp mô hình (có nhớ đệm theo thời gian sửa file). Trả None nếu chưa huấn luyện."""
    if not FILE_MO_HINH.exists():
        return None
    mt = FILE_MO_HINH.stat().st_mtime
    if _cache_mo_hinh["mtime"] != mt:
        import joblib
        _cache_mo_hinh["obj"] = joblib.load(FILE_MO_HINH)
        _cache_mo_hinh["mtime"] = mt
    return _cache_mo_hinh["obj"]


def doc_chi_so():
    if FILE_CHI_SO.exists():
        try:
            return json.loads(FILE_CHI_SO.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def du_bao_24h(df_gan_day: pd.DataFrame, obj=None) -> dict:
    """df_gan_day: chuỗi giờ liên tục gần nhất (>= 72 giờ, kết thúc tại giờ hiện tại, cột CAC_COT).
    Trả {"gio_goc": ISO, "pm25_hien_tai": float, "du_bao": [{"gio","pm25","thap","cao"}...]}."""
    obj = obj or tai_mo_hinh()
    if obj is None:
        raise FileNotFoundError("Chưa có mô hình theo giờ. Chạy: python ml/train_du_bao_gio.py")
    f = tao_dac_trung(df_gan_day)
    hang = f.dropna(subset=["pm25_t", "pm25_lag24", "pm25_tb24"])
    if hang.empty:
        raise ValueError("Dữ liệu gần đây không đủ để dự báo (thiếu PM2.5).")
    # điền khuyết nhẹ cho cột phụ ở hàng cuối (nếu một biến thời tiết bị trống tại giờ cuối)
    cuoi = f.loc[[hang.index[-1]]].copy()
    cuoi = cuoi.ffill(axis=0)
    for c in DAC_TRUNG:
        if c in cuoi.columns and cuoi[c].isna().any():
            cuoi[c] = float(f[c].dropna().iloc[-1]) if f[c].notna().any() else 0.0
    t = cuoi.index[0]
    p_t = float(cuoi["pm25_t"].iloc[0])
    out = []
    for h in BUOC:
        x = _them_buoc(cuoi, h)
        d = float(obj["mo_hinh"].predict(x)[0]) * float(obj.get("alpha", {}).get(h, 1.0))
        v = max(0.0, p_t + d)
        lo, hi = obj["phan_vi_sai_so"].get(str(h), (0.0, 0.0))
        out.append({"gio": (t + pd.Timedelta(hours=h)).strftime("%Y-%m-%dT%H:00"), "pm25": round(v, 1),
                    "thap": round(max(0.0, v + lo), 1), "cao": round(max(0.0, v + hi), 1)})
    return {"gio_goc": t.strftime("%Y-%m-%dT%H:00"), "pm25_hien_tai": round(p_t, 1), "du_bao": out}


def khung_gio_tot_xau(du_bao: list, do_dai: int = 3):
    """Cửa sổ liên tiếp `do_dai` giờ có PM2.5 trung bình thấp nhất / cao nhất. Trả (tot, xau) mỗi cái là dict hoặc None."""
    if len(du_bao) < do_dai:
        return None, None
    v = [x["pm25"] for x in du_bao]
    tb = [sum(v[i:i + do_dai]) / do_dai for i in range(len(v) - do_dai + 1)]
    i_tot, i_xau = int(np.argmin(tb)), int(np.argmax(tb))

    def goi(i):
        return {"tu": du_bao[i]["gio"], "den": du_bao[i + do_dai - 1]["gio"], "pm25_tb": round(tb[i], 1)}
    return goi(i_tot), goi(i_xau)
