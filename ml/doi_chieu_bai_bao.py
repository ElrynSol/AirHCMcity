"""Đối chiếu AirHCM với nghiên cứu đã công bố về dự báo PM2.5 tại TP.HCM và bổ sung 3 phân tích mà bài báo có.

Bài báo đối chiếu: Rakholia R., Le Q., Vu K., Ho B.Q., Carbajo R.S. (2022). "AI-based air quality PM2.5 forecasting models
for developing countries: A case study of Ho Chi Minh City, Vietnam". Urban Climate 46, 101315.
doi:10.1016/j.uclim.2022.101315 — dự báo PM2.5 theo giờ (1–24 giờ) và trung bình trượt 24 giờ, so sánh SGD, CNN-LSTM,
XGBoost, Prophet; phân tích đặc điểm PM2.5 theo thời gian; huấn luyện bằng dữ liệu giai đoạn ngắn để xử lý chuỗi không dừng.

Chạy từ thư mục gốc dự án (khoảng 5–10 phút):
    python ml/doi_chieu_bai_bao.py
Kết quả: frontend/hinh/ml/doi_chieu_bai_bao.json (trang Phương pháp đọc tệp này).

Ba phân tích (cùng dữ liệu du_lieu/gio_cache.csv, cùng đặc trưng với mô hình đang chạy — services/du_bao_gio.py):
1. Đặc điểm theo thời gian: PM2.5 theo giờ trong ngày (ngày thường / cuối tuần), theo ngày trong tuần, theo tháng.
2. So sánh mô hình ở dự báo theo giờ, cùng tập kiểm tra (20% cuối, chia theo thời gian): giữ nguyên (nền), SGD,
   Gradient Boosting, mạng nơ-ron MLP. Khác bài báo: không có XGBoost/CNN-LSTM (máy chủ không cài xgboost/TensorFlow) —
   HistGradientBoosting cùng họ thuật toán với XGBoost, MLP đại diện nhóm mạng nơ-ron; đây KHÔNG phải tái lập bài báo.
3. Cửa sổ huấn luyện: huấn luyện lại mỗi tháng bằng 3/6/12/24 tháng gần nhất hoặc toàn bộ quá khứ.
Số liệu là PM2.5 mô hình CAMS (không phải trạm đo mặt đất như bài báo) nên không so trực tiếp được sai số với bài báo.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC / "backend"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BUOC = [1, 3, 6, 12, 24]
CUA_SO_THANG = [3, 6, 12, 24, None]      # None = toàn bộ quá khứ
DICH = GOC / "frontend" / "hinh" / "ml" / "doi_chieu_bai_bao.json"


def rmse(y, yh):
    return float(np.sqrt(np.mean((y - yh) ** 2)))


def chi_so(y, yh):
    ss = float(np.sum((y - y.mean()) ** 2))
    return {"rmse": rmse(y, yh), "mae": float(np.mean(np.abs(y - yh))), "r2": float(1 - np.sum((y - yh) ** 2) / ss)}


def dac_diem_thoi_gian(df):
    d = df.dropna(subset=["pm2_5"]).copy()
    d["time"] = pd.to_datetime(d["time"])
    cuoi_tuan = d["time"].dt.dayofweek >= 5
    theo_gio = lambda x: [round(float(v), 2) for v in x.groupby(x["time"].dt.hour)["pm2_5"].mean().reindex(range(24))]
    tb_gio = d.groupby(d["time"].dt.hour)["pm2_5"].mean()
    thu = d.groupby(d["time"].dt.dayofweek)["pm2_5"].mean()
    thang = d.groupby(d["time"].dt.month)["pm2_5"].mean()
    return {
        "so_gio": int(len(d)), "tu": str(d["time"].min())[:10], "den": str(d["time"].max())[:10],
        "trung_binh": round(float(d["pm2_5"].mean()), 2),
        "theo_gio_ngay_thuong": theo_gio(d[~cuoi_tuan]), "theo_gio_cuoi_tuan": theo_gio(d[cuoi_tuan]),
        "gio_cao_nhat": int(tb_gio.idxmax()), "gio_thap_nhat": int(tb_gio.idxmin()),
        "pm25_gio_cao_nhat": round(float(tb_gio.max()), 2), "pm25_gio_thap_nhat": round(float(tb_gio.min()), 2),
        "theo_thu": [round(float(v), 2) for v in thu.reindex(range(7))],          # 0 = Thứ 2
        "ngay_thuong": round(float(d.loc[~cuoi_tuan, "pm2_5"].mean()), 2),
        "cuoi_tuan": round(float(d.loc[cuoi_tuan, "pm2_5"].mean()), 2),
        "theo_thang": [round(float(v), 2) for v in thang.reindex(range(1, 13))],
    }


def so_sanh_mo_hinh(X, yd, p0, yt, tt, hh, tr, te):
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.linear_model import SGDRegressor
    from sklearn.neural_network import MLPRegressor
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    ung_vien = {
        "SGD Regressor (tuyến tính)": make_pipeline(StandardScaler(), SGDRegressor(
            loss="huber", epsilon=5.0, alpha=1e-4, max_iter=60, tol=1e-4, random_state=42)),
        "Gradient Boosting (HistGB, cùng họ XGBoost)": HistGradientBoostingRegressor(
            max_iter=250, learning_rate=0.06, max_depth=7, min_samples_leaf=40, l2_regularization=1.0, random_state=42),
        "Mạng nơ-ron MLP (64-32)": make_pipeline(StandardScaler(), MLPRegressor(
            hidden_layer_sizes=(64, 32), early_stopping=True, validation_fraction=0.1, n_iter_no_change=5,
            max_iter=60, batch_size=512, random_state=42)),
    }
    nen = rmse(yt[te], p0[te])
    kq = [{"mo_hinh": "Giữ nguyên giá trị hiện tại (nền)", **chi_so(yt[te], p0[te]), "ky_nang": 0.0, "giay_huan_luyen": 0.0,
           "theo_buoc": {str(h): 0.0 for h in BUOC}}]
    for ten, m in ung_vien.items():
        t0 = time.time()
        m.fit(X[tr], yd[tr])
        du = np.clip(p0[te] + m.predict(X[te]), 0, None)
        cs = chi_so(yt[te], du)
        theo_buoc = {}
        for h in BUOC:
            k = hh[te] == h
            theo_buoc[str(h)] = round(1 - rmse(yt[te][k], du[k]) / rmse(yt[te][k], p0[te][k]), 4)
        kq.append({"mo_hinh": ten, **cs, "ky_nang": round(1 - cs["rmse"] / nen, 4),
                   "giay_huan_luyen": round(time.time() - t0, 1), "theo_buoc": theo_buoc})
        print(f"  {ten:<46} RMSE {cs['rmse']:.2f}  kỹ năng {kq[-1]['ky_nang']:+.3f}  ({kq[-1]['giay_huan_luyen']}s)", flush=True)
    return kq


def cua_so_huan_luyen(X, yd, p0, yt, tt, hh, moc_test):
    """Huấn luyện lại đầu mỗi tháng của giai đoạn kiểm tra, chỉ dùng W tháng ngay trước đó (cách 24 giờ để không rò rỉ nhãn)."""
    from sklearn.ensemble import HistGradientBoostingRegressor
    cac_moc = list(pd.date_range(moc_test, tt.max(), freq="30D")) + [tt.max() + pd.Timedelta(hours=1)]
    kq = []
    for w in CUA_SO_THANG:
        t0 = time.time()
        du_tat, y_tat, p_tat = [], [], []
        for a, b in zip(cac_moc[:-1], cac_moc[1:]):
            te = (tt >= a) & (tt < b)
            tr = tt <= a - pd.Timedelta(hours=24)
            if w is not None:
                tr &= tt > a - pd.Timedelta(days=30 * w)
            if te.sum() < 100 or tr.sum() < 1000:
                continue
            m = HistGradientBoostingRegressor(max_iter=250, learning_rate=0.06, max_depth=7, min_samples_leaf=40,
                                              l2_regularization=1.0, random_state=42).fit(X[tr], yd[tr])
            du_tat.append(np.clip(p0[te] + m.predict(X[te]), 0, None)); y_tat.append(yt[te]); p_tat.append(p0[te])
        du, y, p = map(np.concatenate, (du_tat, y_tat, p_tat))
        cs = chi_so(y, du)
        kq.append({"cua_so_thang": w, "ten": f"{w} tháng gần nhất" if w else "Toàn bộ quá khứ", **cs,
                   "ky_nang": round(1 - cs["rmse"] / rmse(y, p), 4), "so_lan_huan_luyen": len(du_tat),
                   "giay": round(time.time() - t0, 1)})
        print(f"  {kq[-1]['ten']:<22} RMSE {cs['rmse']:.2f}  kỹ năng {kq[-1]['ky_nang']:+.3f}  ({kq[-1]['giay']}s)", flush=True)
    return kq


def main():
    from services import du_bao_gio as dbg
    df = pd.read_csv(GOC / "du_lieu" / "gio_cache.csv")[dbg.CAC_COT]
    print("1. Đặc điểm PM2.5 theo thời gian", flush=True)
    dd = dac_diem_thoi_gian(df)
    print(f"  Cao nhất lúc {dd['gio_cao_nhat']}h ({dd['pm25_gio_cao_nhat']}), thấp nhất lúc {dd['gio_thap_nhat']}h "
          f"({dd['pm25_gio_thap_nhat']}); ngày thường {dd['ngay_thuong']} / cuối tuần {dd['cuoi_tuan']} µg/m³")

    X, yd, p0, yt, tt, hh = dbg.tao_tap_huan_luyen(df, buoc=BUOC)
    X = X.values
    tt = pd.to_datetime(tt)
    moc_test = tt.min() + (tt.max() - tt.min()) * 0.8
    tr, te = tt <= moc_test - pd.Timedelta(hours=24), tt > moc_test
    print(f"2. So sánh mô hình ({int(tr.sum()):,} mẫu huấn luyện, {int(te.sum()):,} mẫu kiểm tra từ {str(moc_test)[:10]})", flush=True)
    ss = so_sanh_mo_hinh(X, yd, p0, yt, tt, hh, tr, te)
    print("3. Cửa sổ huấn luyện (huấn luyện lại mỗi 30 ngày)", flush=True)
    cs = cua_so_huan_luyen(X, yd, p0, yt, tt, hh, moc_test)

    DICH.parent.mkdir(parents=True, exist_ok=True)
    DICH.write_text(json.dumps({
        "cap_nhat": datetime.now().isoformat(timespec="seconds"),
        "bai_bao": {"tac_gia": "Rakholia R., Le Q., Vu K., Ho B.Q., Carbajo R.S.", "nam": 2022,
                    "ten": "AI-based air quality PM2.5 forecasting models for developing countries: A case study of Ho Chi Minh City, Vietnam",
                    "tap_chi": "Urban Climate 46, 101315", "doi": "10.1016/j.uclim.2022.101315"},
        "buoc": BUOC, "kiem_tra_tu": str(moc_test)[:10], "kiem_tra_den": str(tt.max())[:10],
        "so_mau_kiem_tra": int(te.sum()), "so_mau_huan_luyen": int(tr.sum()),
        "dac_diem": dd, "so_sanh": ss, "cua_so": cs,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Đã ghi {DICH.relative_to(GOC)}")


if __name__ == "__main__":
    main()
