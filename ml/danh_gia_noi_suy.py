"""Đánh giá độ phân giải không gian thực sự của dữ liệu và độ chính xác của nội suy IDW.

Chạy từ thư mục gốc dự án:   venv\\Scripts\\python ml\\danh_gia_noi_suy.py
Kết quả: models/danh_gia_noi_suy.json (API /api/v1/phuong-phap và trang Phương pháp đọc tệp này).

Hai câu hỏi được trả lời bằng số liệu trong CSDL:
1. "Độ phân giải hiệu dụng": CAMS là lưới ~0,4° (≈ 44 km), nên nhiều điểm ước tính gần nhau rơi vào CÙNG một ô lưới và
   nhận chuỗi PM2.5 giống hệt nhau. Đếm số chuỗi khác nhau mỗi năm = số ô lưới thực sự mang thông tin.
2. Nội suy IDW chính xác đến đâu: kiểm chéo bỏ một điểm (leave-one-out) theo từng ngày, so với cách đơn giản
   "lấy trung bình các điểm còn lại". Các điểm cùng ô lưới được GỘP thành một điểm (tọa độ trung bình) trước khi kiểm chéo;
   nếu không gộp, bỏ một điểm vẫn còn "bản sao" của nó ở điểm cùng ô → sai số thấp giả tạo.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC / "backend"))
RA = GOC / "models" / "danh_gia_noi_suy.json"
TOI_THIEU_O = 5          # ngày có ít nhất 5 ô lưới khác nhau mới kiểm chéo (ít hơn thì nội suy không có ý nghĩa)


def gop_theo_o_luoi(g: pd.DataFrame, cot="pm25_mean") -> pd.DataFrame:
    """Gộp các điểm có cùng giá trị (cùng ô lưới CAMS) trong một ngày thành một điểm ở tọa độ trung bình. Hàm thuần."""
    v = g[cot].round(3)
    return g.assign(_v=v).groupby("_v").agg(lat=("lat", "mean"), lon=("lon", "mean")).reset_index().rename(columns={"_v": cot})


def so_o_luoi_theo_nam(df: pd.DataFrame) -> list:
    """Mỗi năm: số điểm ước tính, số chuỗi PM2.5 khác nhau (= số ô lưới CAMS thực sự khác nhau)
    và số chuỗi nhiệt độ khác nhau (= số ô lưới khí tượng ERA5/ERA5-Land khác nhau)."""
    kq = []
    for nam, s in df.groupby(pd.to_datetime(df["ngay_do"]).dt.year):
        dem = lambda cot: int(len(s.pivot(index="ngay_do", columns="tram_id", values=cot).round(3).T.drop_duplicates()))
        kq.append({"nam": int(nam), "so_diem": int(s["tram_id"].nunique()), "so_o_luoi_khac_nhau": dem("pm25_mean"),
                   "so_o_luoi_khi_tuong_khac_nhau": dem("nhiet_do_mean")})
    return kq


def kiem_cheo_idw(df: pd.DataFrame) -> dict:
    from services.ban_do_nhiet import sai_so_bo_mot_tram
    e_idw, e_nen, e_idw_khong_gop, e_nen_khong_gop, so_ngay = [], [], [], [], 0
    for _, g in df.groupby("ngay_do"):
        r0 = sai_so_bo_mot_tram(g["lat"].values, g["lon"].values, g["pm25_mean"].values)
        if r0:
            e_idw_khong_gop.append(r0["RMSE_idw"] ** 2); e_nen_khong_gop.append(r0["RMSE_trung_binh_cac_tram_con_lai"] ** 2)
        o = gop_theo_o_luoi(g)
        if len(o) < TOI_THIEU_O:
            continue
        r = sai_so_bo_mot_tram(o["lat"].values, o["lon"].values, o["pm25_mean"].values)
        e_idw.append(r["RMSE_idw"] ** 2); e_nen.append(r["RMSE_trung_binh_cac_tram_con_lai"] ** 2)
        so_ngay += 1
    rm = lambda e: float(np.sqrt(np.mean(e))) if e else None
    kq = {"so_ngay": so_ngay, "toi_thieu_o_luoi_moi_ngay": TOI_THIEU_O,
          "RMSE_idw": rm(e_idw), "RMSE_trung_binh_con_lai": rm(e_nen),
          "khong_gop_o_luoi": {"so_ngay": len(e_idw_khong_gop), "RMSE_idw": rm(e_idw_khong_gop),
                               "RMSE_trung_binh_con_lai": rm(e_nen_khong_gop)}}
    if kq["RMSE_idw"] and kq["RMSE_trung_binh_con_lai"]:
        kq["ky_nang"] = 1 - kq["RMSE_idw"] / kq["RMSE_trung_binh_con_lai"]
    k = kq["khong_gop_o_luoi"]
    if k["RMSE_idw"] and k["RMSE_trung_binh_con_lai"]:
        k["ky_nang"] = 1 - k["RMSE_idw"] / k["RMSE_trung_binh_con_lai"]
    return kq


def main():
    from database import engine
    df = pd.read_sql("""SELECT d.ngay_do, d.tram_id, d.pm25_mean, d.nhiet_do_mean, ST_Y(t.toado::geometry) AS lat, ST_X(t.toado::geometry) AS lon
                        FROM du_lieu_tram_mat_dat d JOIN tram_quan_trac t ON t.id = d.tram_id
                        WHERE t.trang_thai = 'Hoat Dong' AND d.pm25_mean IS NOT NULL""", engine)
    if df.empty:
        sys.exit("CSDL chưa có số liệu PM2.5 (chạy data_pipeline/du_lieu_mo.py --nhap).")
    do_lech = df.groupby("ngay_do")["pm25_mean"].std()
    kq = {"cap_nhat": datetime.now().isoformat(timespec="seconds"),
          "du_lieu": f"{df['ngay_do'].min()} → {df['ngay_do'].max()}", "so_diem": int(df["tram_id"].nunique()),
          "khung_toa_do": {"lat": [round(float(df["lat"].min()), 3), round(float(df["lat"].max()), 3)],
                           "lon": [round(float(df["lon"].min()), 3), round(float(df["lon"].max()), 3)]},
          "o_luoi_theo_nam": so_o_luoi_theo_nam(df),
          "do_lech_chuan_giua_cac_diem_moi_ngay": round(float(do_lech.mean()), 2),
          "kiem_cheo_idw": kiem_cheo_idw(df),
          "dien_giai": ("Số ô lưới khác nhau là độ phân giải không gian THỰC của số liệu CAMS; bản đồ 168 phường/xã là độ phân giải "
                        "HIỂN THỊ do nội suy, không thêm thông tin mới. Kiểm chéo đã gộp các điểm cùng ô lưới để không bị lạc quan giả tạo.")}
    lam_tron = lambda x: ({k: lam_tron(v) for k, v in x.items()} if isinstance(x, dict) else [lam_tron(v) for v in x]
                          if isinstance(x, list) else round(x, 3) if isinstance(x, float) else x)
    RA.write_text(json.dumps(lam_tron(kq), ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    k = kq["kiem_cheo_idw"]
    print(f"{kq['so_diem']} điểm; ô lưới theo năm: " + ", ".join(f"{x['nam']}: {x['so_o_luoi_khac_nhau']}/{x['so_diem']}" for x in kq["o_luoi_theo_nam"]))
    print(f"IDW bỏ một ô ({k['so_ngay']} ngày): RMSE {k['RMSE_idw']:.2f} so với trung bình còn lại {k['RMSE_trung_binh_con_lai']:.2f}"
          f" → kỹ năng {k.get('ky_nang', 0):+.3f}")
    print(f"Đã ghi {RA}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
