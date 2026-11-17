"""Bộ dữ liệu mở của AirHCM: xuất các bảng số liệu môi trường (KHÔNG có dữ liệu cá nhân) ra CSV, hoặc nạp lại vào CSDL mới.

    python data_pipeline/du_lieu_mo.py --xuat    # CSDL → du_lieu/mo/*.csv (để chia sẻ / đưa lên GitHub)
    python data_pipeline/du_lieu_mo.py --nhap    # du_lieu/mo/*.csv → CSDL (chỉ nạp vào bảng đang TRỐNG)

Chỉ xuất: trạm quan trắc, số liệu ngày theo trạm (CAMS/Open-Meteo), số liệu vệ tinh Sentinel-5P.
KHÔNG BAO GIỜ xuất: người dùng, phiên đăng nhập, OTP, liên kết mạng xã hội, thư đã gửi, nhật ký, phản ánh, đăng ký cảnh báo.
Bảng `phuong_xa` có sẵn ở du_lieu/ranh_gioi/phuong_xa_hcm.geojson (máy chủ tự nạp khi khởi động).
"""
import argparse
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC / "data_pipeline"))
THU_MUC = GOC / "du_lieu" / "mo"

BANG = {   # tên tệp → (bảng, câu SELECT xuất)
    "tram_quan_trac.csv": ("tram_quan_trac",
        "SELECT id, ma_tram, ten_tram, ST_Y(toado) AS vi_do, ST_X(toado) AS kinh_do, trang_thai, nhom_o_nhiem "
        "FROM tram_quan_trac ORDER BY id"),
    "du_lieu_ngay_theo_tram.csv": ("du_lieu_tram_mat_dat",
        "SELECT id, tram_id, khu_vuc, ngay_do, pm25_mean, pm10_mean, co_mean, no2_mean, so2_mean, o3_mean, "
        "nhiet_do_mean, do_am_mean, gio_toc_do_mean, mua_tong, pm25_smoothed, pm10_smoothed, o3_smoothed, nguon_du_lieu "
        "FROM du_lieu_tram_mat_dat ORDER BY ngay_do, tram_id"),
    "ve_tinh_sentinel5p.csv": ("du_lieu_gee_tphcm",
        "SELECT id, tram_id, khu_vuc, ngay_do, no2_mean, co_mean, so2_mean FROM du_lieu_gee_tphcm ORDER BY ngay_do, tram_id"),
}


def xuat(engine):
    THU_MUC.mkdir(parents=True, exist_ok=True)
    with engine.connect() as c:
        for tep, (_, sql) in BANG.items():
            df = pd.read_sql(text(sql), c)
            df.to_csv(THU_MUC / tep, index=False, float_format="%.4f")
            print(f"  {tep:<30} {len(df):>7,} dòng  {(THU_MUC / tep).stat().st_size / 1e6:.2f} MB")


def nhap(engine):
    with engine.begin() as c:
        for tep, (bang, _) in BANG.items():
            f = THU_MUC / tep
            if not f.exists():
                print(f"  bỏ qua {tep}: không có tệp"); continue
            if c.execute(text(f"SELECT EXISTS (SELECT 1 FROM {bang})")).scalar():
                print(f"  bỏ qua {bang}: bảng đã có dữ liệu"); continue
            df = pd.read_csv(f)
            if bang == "tram_quan_trac":
                c.execute(text("""INSERT INTO tram_quan_trac (id, ma_tram, ten_tram, toado, trang_thai, nhom_o_nhiem)
                    VALUES (:id, :ma_tram, :ten_tram, ST_SetSRID(ST_MakePoint(:kinh_do, :vi_do), 4326), :trang_thai, :nhom_o_nhiem)"""),
                    df.astype(object).where(df.notna(), None).to_dict("records"))
            else:
                df.to_sql(bang, c, if_exists="append", index=False, method="multi", chunksize=2000)
            c.execute(text(f"SELECT setval(pg_get_serial_sequence('{bang}', 'id'), (SELECT MAX(id) FROM {bang}))"))
            print(f"  {bang:<24} nạp {len(df):,} dòng")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--xuat", action="store_true")
    g.add_argument("--nhap", action="store_true")
    a = ap.parse_args()
    from db_url import get_engine
    (xuat if a.xuat else nhap)(get_engine())


if __name__ == "__main__":
    main()
