"""
Làm mịn không gian (Spatial Downscaling) - phiên bản 2.

Khác bản cũ ở 4 điểm:
1. Xác định "ô lưới" của Open-Meteo từ chính dữ liệu: các trạm luôn có giá trị giống hệt nhau
   thuộc cùng một ô.
2. Đánh giá trung thực: (a) chia theo thời gian, (b) chia theo Ô LƯỚI (ô chưa từng thấy),
   thay vì chia ngẫu nhiên.
3. Bảo toàn trung bình ô: mô hình chỉ quyết định tỉ lệ giữa các trạm trong cùng ô, còn mức
   chung mỗi ngày giữ đúng giá trị gốc. Nhờ đó đỉnh ô nhiễm không bị "co" lại.
4. Ngày chưa có dữ liệu vệ tinh (trễ ~10-12 ngày) vẫn được xử lý, bằng giá trị vệ tinh trung
   bình theo (trạm, tháng) từ lịch sử.

Giới hạn cần nêu rõ trong báo cáo: dữ liệu gốc của các trạm cùng ô giống hệt nhau nên KHÔNG có
số đo thật để kiểm chứng sự khác biệt giữa các trạm trong ô. Phần chênh lệch này là ước lượng
dựa trên dữ liệu vệ tinh, chưa được kiểm chứng độc lập.
"""

import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold
from sqlalchemy import create_engine, text

env_path = Path(__file__).resolve().parent.parent
for _ in range(3):
    if (env_path / ".env").exists():
        load_dotenv(env_path / ".env")
        break
    env_path = env_path.parent

GEE_COLS = ['no2_mean', 'co_mean', 'so2_mean']
DUNG_TOA_DO = False   # True: thêm lat/lon làm đặc trưng (dễ khiến mô hình "nhớ" từng trạm)
FEATURES = GEE_COLS + (['lat', 'lon'] if DUNG_TOA_DO else []) + ['thang']
TARGETS = ['pm25_mean', 'pm10_mean', 'o3_mean']
TI_LE_MIN, TI_LE_MAX = 0.6, 1.4   # giới hạn hệ số điều chỉnh so với giá trị gốc (tham số có thể chỉnh)


import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parent.parent / 'data_pipeline'))
from db_url import get_engine as _get_engine_chung  # noqa: E402


def get_engine():
    """Kết nối CSDL: ưu tiên DATABASE_URL, sau đó DB_* trong .env (data_pipeline/db_url.py)."""
    return _get_engine_chung()


# ----------------------------------------------------------------------------
# 1. Đọc dữ liệu
# ----------------------------------------------------------------------------
def load_all():
    engine = get_engine()
    tram = pd.read_sql("""
        SELECT tram_id, ngay_do, pm25_mean, pm10_mean, o3_mean
        FROM du_lieu_tram_mat_dat WHERE tram_id IS NOT NULL
    """, engine)
    gee = pd.read_sql("""
        SELECT tram_id, ngay_do, no2_mean, co_mean, so2_mean
        FROM du_lieu_gee_tphcm WHERE tram_id IS NOT NULL
    """, engine)
    info = pd.read_sql("""
        SELECT id AS tram_id, ST_Y(toado) AS lat, ST_X(toado) AS lon FROM tram_quan_trac
    """, engine)

    df = tram.merge(gee, on=['tram_id', 'ngay_do'], how='left').merge(info, on='tram_id', how='left')
    return chuan_bi(df)


def chuan_bi(df):
    df = df.copy()
    df['ngay_do'] = pd.to_datetime(df['ngay_do'])
    df['thang'] = df['ngay_do'].dt.month
    df['so2_mean'] = df['so2_mean'].clip(lower=0)
    return df


# ----------------------------------------------------------------------------
# 2. Ô lưới và dữ liệu vệ tinh còn thiếu
# ----------------------------------------------------------------------------
def xac_dinh_o_luoi(df, cot='pm25_mean', nguong=0.9, so_ngay_toi_thieu=30):
    """Gom các trạm có giá trị giống hệt nhau (>= nguong số ngày chung) vào cùng một ô."""
    pv = df.pivot_table(index='ngay_do', columns='tram_id', values=cot)
    ids = list(pv.columns)
    cha = {i: i for i in ids}

    def tim(x):
        while cha[x] != x:
            cha[x] = cha[cha[x]]
            x = cha[x]
        return x

    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            chung = pv[[a, b]].dropna()
            if len(chung) < so_ngay_toi_thieu:
                continue
            if ((chung[a] - chung[b]).abs() < 1e-6).mean() >= nguong:
                cha[tim(a)] = tim(b)

    goc = {i: tim(i) for i in ids}
    nhan = {g: k for k, g in enumerate(sorted(set(goc.values())))}
    return {i: nhan[goc[i]] for i in ids}


def bo_sung_ve_tinh(df):
    """Ngày thiếu vệ tinh: dùng trung bình theo (trạm, tháng), thiếu nữa thì trung bình theo trạm."""
    df = df.copy()
    df['co_ve_tinh_that'] = df[GEE_COLS].notna().all(axis=1)
    that = df[df['co_ve_tinh_that']]
    for c in GEE_COLS:
        tm = that.groupby(['tram_id', 'thang'])[c].mean().rename('_tm').reset_index()
        t = that.groupby('tram_id')[c].mean().rename('_t').reset_index()
        df = df.merge(tm, on=['tram_id', 'thang'], how='left').merge(t, on='tram_id', how='left')
        df[c] = df[c].fillna(df['_tm']).fillna(df['_t'])
        df = df.drop(columns=['_tm', '_t'])
    return df


# ----------------------------------------------------------------------------
# 3. Huấn luyện và đánh giá trung thực

def gan_muc_tieu_tuong_doi(df, target, o_luoi):
    """y_rel = giá trị gốc / trung bình thành phố trong ngày (trung bình các ô, mỗi ô tính 1 lần).
    Bỏ được biến động theo ngày do thời tiết (vệ tinh không dự đoán được), chỉ giữ cấu trúc không gian."""
    d = df.copy()
    d['o'] = d['tram_id'].map(o_luoi).fillna(-d['tram_id'])
    tb_o = d[d[target].notna()].groupby(['ngay_do', 'o'])[target].mean().reset_index()
    tb_tp = tb_o.groupby('ngay_do')[target].mean().rename('tb_tp').reset_index()
    d = d.merge(tb_tp, on='ngay_do', how='left')
    d['y_rel'] = (d[target] / d['tb_tp']).replace([np.inf, -np.inf], np.nan)
    return d


# ----------------------------------------------------------------------------
def tao_mo_hinh():
    return RandomForestRegressor(n_estimators=200, max_depth=10, min_samples_leaf=5,
                                 random_state=42, n_jobs=-1)


def _bao_cao(ten, y_that, y_du_doan):
    r2 = r2_score(y_that, y_du_doan)
    rmse = mean_squared_error(y_that, y_du_doan) ** 0.5
    print(f"    {ten}: R²={r2:.3f}, RMSE={rmse:.3f}")
    return r2, rmse


def danh_gia(df, target, o_luoi):
    """Hai cách đánh giá không rò rỉ dữ liệu. Chỉ dùng các dòng có dữ liệu vệ tinh thật."""
    tap = df[df['co_ve_tinh_that'] & df['y_rel'].notna()].copy()
    tap['o'] = tap['tram_id'].map(o_luoi)
    ket_qua = {}

    # (a) Theo thời gian: huấn luyện trên 80% ngày đầu, kiểm tra trên 20% ngày cuối
    moc = tap['ngay_do'].quantile(0.8)
    tr, te = tap[tap['ngay_do'] <= moc], tap[tap['ngay_do'] > moc]
    if len(te) > 0 and len(tr) > 0:
        m = tao_mo_hinh().fit(tr[FEATURES], tr['y_rel'])
        ket_qua['thoi_gian'] = _bao_cao("Theo thời gian (ngày chưa thấy)", te['y_rel'], m.predict(te[FEATURES]))

    # (b) Theo ô lưới: kiểm tra trên các ô mà mô hình chưa từng thấy
    so_o = tap['o'].nunique()
    if so_o >= 2:
        gkf = GroupKFold(n_splits=min(5, so_o))
        du_doan = pd.Series(index=tap.index, dtype=float)
        for itr, ite in gkf.split(tap, groups=tap['o']):
            m = tao_mo_hinh().fit(tap.iloc[itr][FEATURES], tap.iloc[itr]['y_rel'])
            du_doan.iloc[ite] = m.predict(tap.iloc[ite][FEATURES])
        ket_qua['o_luoi'] = _bao_cao(f"Theo ô lưới ({so_o} ô, ô chưa thấy)", tap['y_rel'], du_doan)
    else:
        print("    Theo ô lưới: bỏ qua (chỉ có 1 ô).")
    return ket_qua


def huan_luyen(df, target):
    tap = df[df['co_ve_tinh_that'] & df['y_rel'].notna()]
    return tao_mo_hinh().fit(tap[FEATURES], tap['y_rel'])


# ----------------------------------------------------------------------------
# 4. Áp dụng: mô hình quyết định tỉ lệ giữa các trạm trong ô, mức chung giữ nguyên
# ----------------------------------------------------------------------------
def ap_dung(df, model, target, o_luoi):
    d = df.copy()
    ok = d[FEATURES].notna().all(axis=1) & d[target].notna()
    d['du_doan'] = np.nan
    d.loc[ok, 'du_doan'] = model.predict(d.loc[ok, FEATURES])

    d['o'] = d['tram_id'].map(o_luoi)
    d['o'] = d['o'].fillna(-d['tram_id'])            # trạm chưa xác định được ô -> ô riêng
    d['tb_o'] = d.groupby(['ngay_do', 'o'])['du_doan'].transform('mean')

    ti_le = (d['du_doan'] / d['tb_o']).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    d['ti_le'] = ti_le.clip(TI_LE_MIN, TI_LE_MAX)
    d['smoothed'] = d[target] * d['ti_le']
    return d


def bao_cao_tac_dong(d, target):
    co_gt = d[target].notna()
    nhieu_tram = d.groupby(['ngay_do', 'o'])['tram_id'].transform('count') >= 2
    chenh = d[co_gt & nhieu_tram].groupby(['ngay_do', 'o'])['smoothed'].agg(lambda s: s.max() - s.min())
    print(f"    Biên độ: gốc max={d.loc[co_gt, target].max():.2f}, làm mịn max={d.loc[co_gt, 'smoothed'].max():.2f}")
    print(f"    Chênh lệch trung bình giữa các trạm cùng ô: {chenh.mean():.2f} (gốc = 0 vì giống hệt nhau)")
    print(f"    Tỉ lệ dòng bị chặn ở giới hạn [{TI_LE_MIN}, {TI_LE_MAX}]: "
          f"{((d['ti_le'] <= TI_LE_MIN) | (d['ti_le'] >= TI_LE_MAX)).mean():.1%}")
    print(f"    Số dòng dùng vệ tinh bổ sung (ngày trễ): {(~d['co_ve_tinh_that']).sum()}")


# ----------------------------------------------------------------------------
# 5. Lưu CSDL
# ----------------------------------------------------------------------------
def luu_db(d, target):
    col = f"{target.replace('_mean', '')}_smoothed"
    ghi = d[d['smoothed'].notna()]
    rows = [
        {'val': float(v), 'tram_id': int(t), 'ngay_do': n}
        for v, t, n in zip(ghi['smoothed'], ghi['tram_id'], ghi['ngay_do'].dt.date)
    ]
    with get_engine().begin() as conn:
        conn.execute(text(f"ALTER TABLE du_lieu_tram_mat_dat ADD COLUMN IF NOT EXISTS {col} DOUBLE PRECISION"))
        conn.execute(text(f"UPDATE du_lieu_tram_mat_dat SET {col} = :val "
                          f"WHERE tram_id = :tram_id AND ngay_do = :ngay_do"), rows)
    print(f"    Đã lưu {len(rows)} giá trị '{col}' vào CSDL.")


if __name__ == "__main__":
    df = bo_sung_ve_tinh(load_all())
    o_luoi = xac_dinh_o_luoi(df)
    so_o = len(set(o_luoi.values()))
    print(f"[1] {len(df)} dòng, {df['tram_id'].nunique()} trạm, xác định được {so_o} ô lưới Open-Meteo:")
    for o in sorted(set(o_luoi.values())):
        print(f"    Ô {o}: trạm id {sorted(t for t, k in o_luoi.items() if k == o)}")

    os.makedirs("models", exist_ok=True)
    for target in TARGETS:
        print(f"\n=== {target} ===")
        d0 = gan_muc_tieu_tuong_doi(df, target, o_luoi)
        print("[2] Đánh giá (mục tiêu: tỉ lệ so với trung bình thành phố):")
        danh_gia(d0, target, o_luoi)
        print("[3] Huấn luyện mô hình cuối và áp dụng:")
        model = huan_luyen(d0, target)
        joblib.dump(model, f"models/downscale_{target}.pkl")
        d = ap_dung(d0, model, target, o_luoi)
        bao_cao_tac_dong(d, target)
        luu_db(d, target)

    print("\nHOÀN TẤT.")