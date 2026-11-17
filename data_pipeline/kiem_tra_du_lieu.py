"""Kiểm tra chất lượng dữ liệu trong CSDL (CHỈ ĐỌC, không sửa gì).

Chạy từ THƯ MỤC GỐC dự án:   python data_pipeline/kiem_tra_du_lieu.py
Mặc định kiểm tra du_lieu_tram_mat_dat và du_lieu_gee_tphcm; thêm bảng khác: --bang ten_bang
Kết quả in ra màn hình và lưu models/bao_cao_chat_luong_du_lieu.json. Dán phần in ra cho người đánh giá.

Nó trả lời: bảng có bao nhiêu dòng/ngày, thiếu ngày nào, có trùng không, giá trị nào phi lý, cột nào thiếu nhiều,
cột nào đứng yên (cảm biến/nguồn hỏng), dữ liệu mới nhất đến ngày nào.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

GOC = Path(__file__).resolve().parent.parent
# Khoảng hợp lý vật lý cho TP.HCM (cột lạ không có trong bảng này thì bỏ qua)
HOP_LY = {"pm25_mean": (0, 500), "pm10_mean": (0, 800), "o3_mean": (0, 400), "nhiet_do_mean": (15, 42),
          "do_am_mean": (0, 100), "gio_toc_do_mean": (0, 40), "mua_tong": (0, 400), "no2_mean": (0, None),
          "co_mean": (0, None), "so2_mean": (None, None)}


def engine_tu_env():
    from dotenv import load_dotenv
    from sqlalchemy import create_engine
    from urllib.parse import quote_plus
    load_dotenv(GOC / ".env")
    g = os.getenv
    url = g("DATABASE_URL") or (f"postgresql://{g('DB_USER')}:{quote_plus(g('DB_PASS') or '')}@{g('DB_HOST')}:{g('DB_PORT')}/{g('DB_NAME')}")
    return create_engine(url)


def chay_dai_nhat_giong_nhau(s: pd.Series):
    s = s.dropna()
    if s.empty:
        return 0
    return int((s.groupby((s != s.shift()).cumsum()).transform("size")).max())


def kiem_tra_bang(df: pd.DataFrame, ten: str, cot_ngay="ngay_do", cot_tram=None):
    """df đã đọc vào bộ nhớ. Trả về dict kết quả + danh sách 'van_de' bằng tiếng Việt."""
    van_de, kq = [], {"bang": ten, "so_dong": int(len(df)), "cot": list(df.columns)}
    if cot_ngay not in df:
        return {**kq, "van_de": [f"Không có cột ngày '{cot_ngay}'"]}
    d = pd.to_datetime(df[cot_ngay], errors="coerce")
    if d.isna().any():
        van_de.append(f"{int(d.isna().sum())} dòng có ngày không đọc được")
    ngay = d.dropna().dt.normalize()
    kq.update({"ngay_dau": str(ngay.min().date()), "ngay_cuoi": str(ngay.max().date()), "so_ngay_khac_nhau": int(ngay.nunique())})
    day_du = pd.date_range(ngay.min(), ngay.max(), freq="D")
    thieu = day_du.difference(ngay.unique())
    kq["so_ngay_thieu_trong_khoang"] = int(len(thieu))
    if len(thieu):
        # gom các ngày thiếu liên tiếp thành đoạn
        doan, cur = [], [thieu[0]]
        for x in thieu[1:]:
            if (x - cur[-1]).days == 1: cur.append(x)
            else: doan.append(cur); cur = [x]
        doan.append(cur)
        dai = sorted(doan, key=len, reverse=True)[:5]
        kq["doan_thieu_dai_nhat"] = [f"{x[0].date()} → {x[-1].date()} ({len(x)} ngày)" for x in dai]
        van_de.append(f"Thiếu {len(thieu)} ngày trong khoảng {ngay.min().date()} → {ngay.max().date()}; đoạn dài nhất: {kq['doan_thieu_dai_nhat'][0]}")
    tre = (pd.Timestamp.today().normalize() - ngay.max()).days
    kq["do_tre_ngay_cuoi_so_voi_hom_nay"] = int(tre)
    if tre > 2:
        van_de.append(f"Dữ liệu mới nhất là {ngay.max().date()}, cũ {tre} ngày")
    khoa = [cot_ngay] + ([cot_tram] if cot_tram and cot_tram in df else [])
    trung = int(df.duplicated(subset=khoa).sum())
    kq["dong_trung_khoa"] = trung
    if trung:
        van_de.append(f"{trung} dòng trùng khóa {khoa} (cùng ngày/trạm xuất hiện nhiều lần)")
    kq["dong_moi_ngay"] = {"trung_vi": float(df.groupby(d.dt.normalize()).size().median()),
                           "toi_da": int(df.groupby(d.dt.normalize()).size().max())}
    cot_so, tc = {}, df.select_dtypes("number").columns
    for c in tc:
        s = df[c]
        t = {"thieu_pct": round(float(s.isna().mean() * 100), 1), "min": _f(s.min()), "max": _f(s.max()), "tb": _f(s.mean()),
             "so_giong_nhau_lien_tiep_max": chay_dai_nhat_giong_nhau(s)}
        if t["thieu_pct"] > 20:
            van_de.append(f"Cột {c}: thiếu {t['thieu_pct']}% giá trị")
        if t["so_giong_nhau_lien_tiep_max"] >= 14 and s.nunique() > 1:
            van_de.append(f"Cột {c}: có đoạn {t['so_giong_nhau_lien_tiep_max']} dòng liên tiếp giống hệt nhau (nghi nguồn đứng yên/điền khuyết)")
        gioi = HOP_LY.get(c)
        if gioi:
            lo, hi = gioi
            ngoai = int(((s < lo) if lo is not None else pd.Series(False, index=s.index)).sum() +
                        ((s > hi) if hi is not None else pd.Series(False, index=s.index)).sum())
            t["ngoai_khoang_hop_ly"] = ngoai
            if ngoai:
                van_de.append(f"Cột {c}: {ngoai} giá trị ngoài khoảng hợp lý {gioi}")
        if s.notna().sum() > 30:
            z = (s - s.mean()) / (s.std() or 1)
            t["so_diem_lech_>5_do_lech_chuan"] = int((z.abs() > 5).sum())
        cot_so[c] = t
    kq["cot_so"] = cot_so
    if {"pm25_mean", "pm10_mean"} <= set(df.columns):
        n = int((df["pm25_mean"] > df["pm10_mean"]).sum())
        kq["pm25_lon_hon_pm10"] = n
        if n > 0.02 * len(df):
            van_de.append(f"{n} dòng có PM2.5 > PM10 (không hợp lý vật lý; PM2.5 là một phần của PM10)")
    kq["van_de"] = van_de
    return kq


def _f(x):
    return None if pd.isna(x) else round(float(x), 4)


def in_bao_cao(ds):
    for k in ds:
        print(f"\n=== {k['bang']} ===")
        if "ngay_dau" in k:
            print(f"Dòng: {k['so_dong']} · ngày {k['ngay_dau']} → {k['ngay_cuoi']} · {k['so_ngay_khac_nhau']} ngày khác nhau · "
                  f"thiếu {k['so_ngay_thieu_trong_khoang']} ngày · ~{k['dong_moi_ngay']['trung_vi']:.0f} dòng/ngày · trễ {k['do_tre_ngay_cuoi_so_voi_hom_nay']} ngày")
        for c, t in k.get("cot_so", {}).items():
            print(f"  {c:<18} thiếu {t['thieu_pct']:>5}%  min {t['min']}  max {t['max']}  tb {t['tb']}")
        print("VẤN ĐỀ:" if k["van_de"] else "Không phát hiện vấn đề rõ ràng.")
        for v in k["van_de"]:
            print("  - " + v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bang", action="append", help="tên bảng thêm (mặc định 2 bảng chính)")
    ap.add_argument("--cot-tram", default=None, help="tên cột mã trạm/ô lưới để kiểm tra trùng (nếu biết)")
    a = ap.parse_args()
    eng = engine_tu_env()
    cac = a.bang or ["du_lieu_tram_mat_dat", "du_lieu_gee_tphcm"]
    ds = []
    for b in cac:
        df = pd.read_sql(f"SELECT * FROM {b}", eng)     # chỉ SELECT
        ds.append(kiem_tra_bang(df, b, cot_tram=a.cot_tram))
    in_bao_cao(ds)
    ra = GOC / "models" / "bao_cao_chat_luong_du_lieu.json"
    ra.parent.mkdir(exist_ok=True)
    ra.write_text(json.dumps(ds, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\nĐã lưu {ra}")


if __name__ == "__main__":
    main()
