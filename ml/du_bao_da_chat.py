"""Dự báo ngày mai cho từng chất có nồng độ mặt đất: PM2.5, PM10, O₃ (trung bình thành phố, số liệu CAMS trong CSDL).

Mỗi chất: nhãn y_{t+1}; đặc trưng y_t, y_{t−1}, y_{t−2}, TB 3 và 7 ngày, độ lệch chuẩn 7 ngày, tháng (sin/cos).
So sánh 3 cách trên 30% thời gian cuối: "mai = hôm nay", hồi quy tuyến tính (Ridge), Random Forest; kỹ năng = 1 − RMSE/RMSE_persistence
kèm khoảng tin cậy 95% bootstrap theo khối 7 ngày; tách mùa khô (12–4) / mùa mưa (5–11).

NO₂, CO, SO₂: hệ thống chỉ có CỘT KHÍ VỆ TINH Sentinel-5P (mol/m², trễ 2–3 tuần), không phải nồng độ sát mặt đất (µg/m³)
→ KHÔNG dự báo và KHÔNG so với QCVN; ghi rõ trong kết quả. O₃: QCVN dùng trung bình 8 giờ (120 µg/Nm³); số liệu ở đây là trung bình
ngày nên chỉ dùng để xem xu hướng, không kết luận vượt chuẩn.

Chạy:  python ml/du_bao_da_chat.py   → models/du_bao_da_chat.json, models/du_bao_da_chat.joblib
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC / "ml"))
CHAT = {"pm25": ("PM2.5", "pm25_mean"), "pm10": ("PM10", "pm10_mean"), "o3": ("O₃ (TB ngày)", "o3_mean")}
DAC_TRUNG = ["y", "lag1", "lag2", "tb3", "tb7", "ls7", "thang_sin", "thang_cos"]
SEED = 42


def doc_chuoi() -> pd.DataFrame:
    import predict as pr   # dùng lại cách kết nối CSDL của predict.py
    from sqlalchemy import create_engine
    from dotenv import load_dotenv
    import os
    from urllib.parse import quote_plus
    load_dotenv(GOC / ".env"); g = os.getenv
    url = g("DATABASE_URL") or f"postgresql://{g('DB_USER')}:{quote_plus(g('DB_PASS') or '')}@{g('DB_HOST')}:{g('DB_PORT')}/{g('DB_NAME')}"
    df = pd.read_sql("SELECT ngay_do, AVG(pm25_mean) pm25_mean, AVG(pm10_mean) pm10_mean, AVG(o3_mean) o3_mean "
                     "FROM du_lieu_tram_mat_dat GROUP BY ngay_do ORDER BY ngay_do", create_engine(url))
    df["ngay_do"] = pd.to_datetime(df["ngay_do"])
    return df


def tao_dac_trung(s: pd.Series) -> pd.DataFrame:
    """s: chuỗi theo ngày (index liên tục). Trả bảng đặc trưng tại ngày t và nhãn y_{t+1}."""
    b = pd.DataFrame({"y": s})
    b["lag1"], b["lag2"] = s.shift(1), s.shift(2)
    b["tb3"], b["tb7"], b["ls7"] = s.rolling(3).mean(), s.rolling(7).mean(), s.rolling(7).std()
    thang = (s.index + pd.Timedelta(days=1)).month
    b["thang_sin"], b["thang_cos"] = np.sin(2 * np.pi * thang / 12), np.cos(2 * np.pi * thang / 12)
    b["nhan"] = s.shift(-1)
    return b


def _ci(y, p, base, so_lan=2000, khoi=7):
    rng = np.random.default_rng(SEED); n = len(y); dau = np.arange(0, n - khoi + 1); kq = []
    for _ in range(so_lan):
        idx = np.concatenate([np.arange(a, a + khoi) for a in rng.choice(dau, int(np.ceil(n / khoi)))])[:n]
        kq.append(1 - np.sqrt(np.mean((p[idx] - y[idx]) ** 2)) / np.sqrt(np.mean((base[idx] - y[idx]) ** 2)))
    return {"thap": round(float(np.percentile(kq, 2.5)), 3), "cao": round(float(np.percentile(kq, 97.5)), 3)}


def danh_gia_chat(s: pd.Series, ti_le_test=0.3):
    b = tao_dac_trung(s).dropna()
    n_te = int(len(b) * ti_le_test)
    tr, te = b.iloc[:-n_te], b.iloc[-n_te:]
    y = te["nhan"].values
    ridge = make_pipeline(StandardScaler(), Ridge(alpha=1.0)).fit(tr[DAC_TRUNG], tr["nhan"])
    rf = RandomForestRegressor(n_estimators=300, min_samples_leaf=5, max_features=0.7, random_state=SEED, n_jobs=-1).fit(tr[DAC_TRUNG], tr["nhan"])
    du = {"Mai = hôm nay": te["y"].values, "Hồi quy tuyến tính": ridge.predict(te[DAC_TRUNG]), "Random Forest": rf.predict(te[DAC_TRUNG])}
    base = du["Mai = hôm nay"]; rb = float(np.sqrt(np.mean((base - y) ** 2)))
    mua = np.where((te.index + pd.Timedelta(days=1)).month.isin([12, 1, 2, 3, 4]), "khô", "mưa")
    kq = {}
    for ten, p in du.items():
        e = p - y; rmse = float(np.sqrt(np.mean(e ** 2)))
        x = {"MAE": round(float(np.mean(np.abs(e))), 2), "RMSE": round(rmse, 2), "bias": round(float(e.mean()), 2), "ky_nang": round(1 - rmse / rb, 3)}
        if ten != "Mai = hôm nay":
            x["ky_nang_ci95"] = _ci(y, p, base)
        x["theo_mua"] = {}
        for m in ("khô", "mưa"):
            k = mua == m
            if k.sum() >= 15:
                r_m, r_b = np.sqrt(np.mean((p[k] - y[k]) ** 2)), np.sqrt(np.mean((base[k] - y[k]) ** 2))
                x["theo_mua"][m] = {"so_ngay": int(k.sum()), "ky_nang": round(float(1 - r_m / r_b), 3)}
        kq[ten] = x
    tot = max((t for t in kq if t != "Mai = hôm nay"), key=lambda t: kq[t]["ky_nang"])
    co_y_nghia = kq[tot]["ky_nang_ci95"]["thap"] > 0
    return {"so_ngay_huan_luyen": len(tr), "so_ngay_kiem_tra": len(te), "kiem_tra_tu": str((te.index[0] + pd.Timedelta(days=1)).date()),
            "mo_hinh": kq, "mo_hinh_chon": tot if co_y_nghia else "Mai = hôm nay",
            "ly_do_chon": (f"{tot} tốt hơn có ý nghĩa thống kê" if co_y_nghia else
                           "chưa mô hình nào hơn \"mai = hôm nay\" có ý nghĩa thống kê → dùng \"mai = hôm nay\"")}, {"ridge": ridge, "rf": rf}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    df = doc_chuoi()
    df = df.set_index("ngay_do").asfreq("D")
    kq, mo_hinh = {}, {}
    for ma, (ten, cot) in CHAT.items():
        s = df[cot].interpolate(limit=2)
        dg, mh = danh_gia_chat(s)
        b = tao_dac_trung(s).dropna()
        mh["rf"].fit(b[DAC_TRUNG], b["nhan"]); mh["ridge"].fit(b[DAC_TRUNG], b["nhan"])   # huấn luyện lại trên toàn bộ để vận hành
        kq[ma] = {"ten": ten, **dg}; mo_hinh[ma] = mh
        x = dg["mo_hinh"]
        print(f"{ten:<14} chọn: {dg['mo_hinh_chon']:<18} | RF kỹ năng {x['Random Forest']['ky_nang']:+.3f} CI {x['Random Forest']['ky_nang_ci95']} "
              f"| Ridge {x['Hồi quy tuyến tính']['ky_nang']:+.3f} CI {x['Hồi quy tuyến tính']['ky_nang_ci95']}")
    kq_tong = {"cap_nhat": datetime.now().isoformat(timespec="seconds"), "du_lieu": f"{df.index.min():%d/%m/%Y} → {df.index.max():%d/%m/%Y}",
               "chat": kq, "khong_du_bao": {"NO2, CO, SO2": "CAMS có NO2, CO, SO2 nhưng các khí này phát thải tại chỗ (giao thông, công nghiệp) và tồn tại ngắn, lưới 44 km khó đại diện cho nồng độ ở phường; chưa có số đo mặt đất nào của ba khí để kiểm chứng; số liệu vệ tinh là lượng khí cả cột (mol/m²), trễ 1–2 tuần → chưa dự báo, chỉ dùng theo dõi hiện trạng và phân tích độ nhạy."
                                                            "mặt đất → không dự báo, không so với QCVN."},
               "luu_y": "Số liệu là trung bình thành phố từ mô hình CAMS. O₃ là trung bình ngày; QCVN dùng trung bình 8 giờ nên không kết luận vượt chuẩn."}
    (GOC / "models" / "du_bao_da_chat.json").write_text(json.dumps(kq_tong, ensure_ascii=False, indent=1), encoding="utf-8")
    joblib.dump({"mo_hinh": mo_hinh, "dac_trung": DAC_TRUNG, "chat": CHAT, "chon": {m: kq[m]["mo_hinh_chon"] for m in kq}},
                GOC / "models" / "du_bao_da_chat.joblib")
    print("Đã ghi models/du_bao_da_chat.json và .joblib")


if __name__ == "__main__":
    main()
