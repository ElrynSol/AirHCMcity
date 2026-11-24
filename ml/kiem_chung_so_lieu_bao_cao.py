"""In lại các con số trong báo cáo đồ án để kiểm chứng (dùng khi bảo vệ).

Chạy từ thư mục gốc dự án:   python ml/kiem_chung_so_lieu_bao_cao.py
- Phần A tính lại trực tiếp từ CSDL: Bảng 1.1, Hình 1.2 (theo tháng, hệ số tương quan), Bảng 1.2, Bảng 3.3.
- Phần B đọc các tệp kết quả mà script huấn luyện đã ghi ra (models/*.json, ml/notebooks/ket_qua/*.json):
  Bảng 3.4 – 3.12 và các số ở trang Phương pháp.
Script chỉ đọc, không sửa dữ liệu.
"""
import json
import sys
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC / "backend"))
import pandas as pd  # noqa: E402
from sqlalchemy import text  # noqa: E402
from database import engine  # noqa: E402

pd.set_option("display.width", 160)


def tieu_de(t):
    print("\n" + "=" * 100 + f"\n{t}\n" + "=" * 100)


def doc(ten):
    return json.loads((GOC / ten).read_text(encoding="utf-8"))


# ------------------------------------------------------------------ A. TÍNH LẠI TỪ CSDL
tieu_de("BẢNG 1.1 – PM2.5 trung bình ngày theo năm (trung bình 17 điểm mỗi ngày, số liệu CAMS)")
ngay = pd.read_sql("SELECT ngay_do, AVG(pm25_mean) AS pm25, AVG(gio_toc_do_mean) AS gio, AVG(mua_tong) AS mua "
                   "FROM du_lieu_tram_mat_dat WHERE pm25_mean IS NOT NULL GROUP BY ngay_do ORDER BY ngay_do", engine)
ngay["ngay_do"] = pd.to_datetime(ngay["ngay_do"])
ngay["nam"] = ngay["ngay_do"].dt.year
ngay["qcvn"] = ngay["ngay_do"].dt.year.map(lambda n: 45 if n >= 2026 else 50)   # QCVN 05:2023: 50 đến 2025, 45 từ 2026
bang = ngay.groupby("nam").agg(so_ngay=("pm25", "size"), trung_binh=("pm25", "mean"), cao_nhat=("pm25", "max"),
                               tren_15_WHO=("pm25", lambda x: int((x > 15).sum())), tren_25=("pm25", lambda x: int((x > 25).sum())))
bang["vuot_QCVN"] = ngay.groupby("nam").apply(lambda g: int((g["pm25"] > g["qcvn"]).sum()))
print(bang.round(1).to_string())
print(f"Tổng số ngày: {len(ngay)} ({ngay.ngay_do.min().date()} → {ngay.ngay_do.max().date()}); trung bình chung {ngay.pm25.mean():.1f} µg/m³")

tieu_de("HÌNH 1.2 – Trung bình theo tháng và hệ số tương quan Pearson (theo ngày)")
ngay["thang"] = ngay["ngay_do"].dt.month
print(ngay.groupby("thang")[["pm25", "gio", "mua"]].mean().round(1).T.to_string())
print(f"r(PM2.5, tốc độ gió) = {ngay.pm25.corr(ngay.gio):.2f}   |   r(PM2.5, lượng mưa) = {ngay.pm25.corr(ngay.mua):.2f}")

tieu_de("BẢNG 1.2 – 17 điểm ước tính và phường/xã chứa điểm (PostGIS ST_Contains)")
with engine.connect() as c:
    for r in c.execute(text("""SELECT t.ma_tram, t.ten_tram, ST_Y(t.toado) lat, ST_X(t.toado) lon,
            (SELECT p.ten_day_du FROM phuong_xa p WHERE ST_Contains(p.geom, t.toado) LIMIT 1) phuong
            FROM tram_quan_trac t ORDER BY t.ma_tram""")):
        print(f"{r.ma_tram:4} {r.ten_tram:45} {r.phuong or '':25} {r.lat:.4f}; {r.lon:.4f}")

tieu_de("BẢNG 3.3 – Số bản ghi trong CSDL")
with engine.connect() as c:
    for bang_ten, cot in [("du_lieu_tram_mat_dat", "ngay_do"), ("du_lieu_gee_tphcm", "ngay_do"), ("do_that_gio", "gio"), ("phuong_xa", None),
                          ("lich_su_dong_bo", None), ("nhat_ky_he_thong", None)]:
        q = f"SELECT COUNT(*), MIN({cot}), MAX({cot}) FROM {bang_ten}" if cot else f"SELECT COUNT(*) FROM {bang_ten}"
        print(bang_ten, c.execute(text(q)).fetchone())

# ------------------------------------------------------------------ B. ĐỌC TỆP KẾT QUẢ ĐÃ HUẤN LUYỆN
tieu_de("BẢNG 3.4 – Đối chiếu CAMS với số đo thật (models/doi_chieu_tram_that.json, tạo bởi data_pipeline/doi_chieu_tram_that.py)")
for t in doc("models/doi_chieu_tram_that.json")["tram"]:
    for k in ("theo_ngay", "theo_gio"):
        v = t.get(k)
        if v:
            print(f"{t['tram']['ten'][:30]:30} {k:9} n={v.get('so_ngay') or v.get('so_gio'):>6}  TB thật={v['tb_do_that']:.1f}  TB CAMS={v['tb_cams']:.1f}  "
                  f"MAE={v['MAE']:.1f}  r={v['pearson_r']:.2f}")
            break

tieu_de("BẢNG 3.5 / 3.6 / 3.7 – Ba thực nghiệm notebook (ml/notebooks/ket_qua/*.json, tạo bởi ml/notebooks/xuat_bieu_do.py)")
for ten in ("hoi_quy_chi_so", "phan_loai_chi_so", "chuoi_thoi_gian_chi_so"):
    d = doc(f"ml/notebooks/ket_qua/{ten}.json")
    print(f"\n{ten}:", {k: v for k, v in d.items() if k != "mo_hinh"})
    print(pd.DataFrame(d["mo_hinh"]).round(3).to_string(index=False))

tieu_de("BẢNG 3.8 – Dự báo theo giờ (models/du_bao_gio_chi_so.json, tạo bởi ml/train_du_bao_gio.py)")
g = doc("models/du_bao_gio_chi_so.json")
print("số mẫu", g["so_mau"], "| kiểm tra từ", g["kiem_tra_tu"], "| kỹ năng chung", round(g["tong"]["ky_nang_so_voi_persistence"], 3))
for b in ("1", "3", "6", "12", "24"):
    v = g["theo_buoc"][b]
    print(f"bước {b:>2} giờ: RMSE={v['rmse']:.2f} MAE={v['mae']:.2f} R²={v['r2']:.3f} RMSE mốc={v['rmse_persistence']:.2f} kỹ năng={v['ky_nang_so_voi_persistence']:+.3f}")

tieu_de("BẢNG 3.9 – Ước lượng trong ngày / dự báo ngày kế tiếp (models/model_metadata.json, tạo bởi ml/train_model.py)")
for bt, v in doc("models/model_metadata.json")["danh_gia"]["mo_hinh"].items():
    print(f"\n{bt}: {v['so_mau_kiem_tra']} ngày kiểm tra từ {v['kiem_tra_tu']}")
    for mh in ("random_forest", "hoi_quy_tuyen_tinh", "cay_quyet_dinh"):
        x = v[mh]; print(f"  {mh:20} RMSE={x['RMSE']:.2f} R²={x['R2']:.3f} kỹ năng={x['ky_nang_so_voi_hom_qua']:+.3f}", "KTC", x.get("ky_nang_ci95_bootstrap", ""))
    print("  kiểm chéo cuốn chiếu:", v["kiem_cheo_cuon_chieu"]["gop"])

tieu_de("BẢNG 3.10 – Dự báo ngày kế tiếp nhiều chất (models/du_bao_da_chat.json, tạo bởi ml/du_bao_da_chat.py)")
for chat, v in doc("models/du_bao_da_chat.json")["chat"].items():
    for mh, x in v["mo_hinh"].items():
        print(f"{chat:5} {mh:22} MAE={x['MAE']:.2f} RMSE={x['RMSE']:.2f} kỹ năng={x['ky_nang']:+.3f} KTC={x.get('ky_nang_ci95', '')}")

tieu_de("BẢNG 3.11 – Dự báo từ số đo thật CMT8 (models/mo_hinh_tram_that.json, tạo bởi ml/mo_hinh_tram_that.py)")
for mh, x in doc("models/mo_hinh_tram_that.json")["mo_hinh"].items():
    print(f"{mh:28} MAE={x['MAE']:.2f} RMSE={x['RMSE']:.2f} r={x['r']:.3f} kỹ năng={x['ky_nang']:+.3f} KTC={x.get('ky_nang_ci95', '')}")

tieu_de("BẢNG 3.12 – Mô hình theo điểm cho bản đồ nhiệt (models/diem_chi_so.json, tạo bởi ml/train_diem.py)")
d = doc("models/diem_chi_so.json"); print(d["random_forest"]); print(d["khong_gian"])

tieu_de("DỰ BÁO XÁC SUẤT (models/danh_gia_xac_suat.json, tạo bởi ml/danh_gia_xac_suat.py)")
d = doc("models/danh_gia_xac_suat.json"); print({k: d[k] for k in ("so_ngay", "tu", "den", "MAE", "PICP_80")}, d["xac_suat"]["who_15"]["Brier"], d["xac_suat"]["who_15"]["BSS"])
