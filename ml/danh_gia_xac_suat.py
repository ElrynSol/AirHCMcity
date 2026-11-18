"""Kiểm chứng độ tin cậy của dự báo XÁC SUẤT (mô hình theo ngày) trên các ngày mô hình CHƯA từng học.

Mô hình lưu cho máy chủ được huấn luyện trên dữ liệu đến `data_range` trong models/model_metadata.pkl; mọi ngày sau đó
là tập kiểm tra độc lập theo thời gian. Với mỗi ngày t trong tập đó: dự báo 1 bước từ dữ liệu đến t−1, so với PM2.5 thật ngày t.

Chỉ số (theo đề cương "Hệ thống dự báo, phân tích xác suất và truy tìm nguồn thải"):
- PICP = #{L ≤ y ≤ U} / N cho khoảng dự báo 80% (mục tiêu ≈ 80%).
- Brier = mean(p − o)², o ∈ {0,1}, cho xác suất vượt WHO 15 và QCVN 45 µg/m³; so với Brier của tần suất khí hậu (base rate).
- Bảng độ tin cậy: chia xác suất dự báo thành các khoảng, so tần suất vượt thực tế.
- MAE, RMSE, bias = mean(ŷ − y), kỹ năng so với "mai = hôm nay".

Chạy:  python ml/danh_gia_xac_suat.py        → models/danh_gia_xac_suat.json
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC / "ml"))
import predict as pr  # noqa: E402

NGUONG = {"who_15": 15.0, "qcvn_45": 45.0}


def danh_gia(df: pd.DataFrame, model, meta, tu_ngay: pd.Timestamp) -> dict:
    d = df.dropna(subset=["pm25_mean"]).sort_values("ngay_do").reset_index(drop=True)
    dong = []
    for ngay in d.loc[d["ngay_do"] >= tu_ngay, "ngay_do"]:
        truoc = d[d["ngay_do"] < ngay].tail(60)
        r = pr.du_bao_tu_chuoi(truoc, model, meta, 1, ngay - pd.Timedelta(days=1))
        if isinstance(r, dict) or not r[0] or r[0][0]["ngay"] != str(ngay.date()):
            continue
        x, y = r[0][0], float(d.loc[d["ngay_do"] == ngay, "pm25_mean"].iloc[0])
        dong.append({"ngay": str(ngay.date()), "y": y, "yhat": x["pm25"], "L": x["khoang_80"]["thap"], "U": x["khoang_80"]["cao"],
                     "nen": float(truoc["pm25_mean"].iloc[-1]), **{f"p_{k}": v for k, v in x["xac_suat_vuot"].items()}})
    if not dong:
        return {"error": "Không có ngày nào sau mốc huấn luyện để kiểm chứng."}
    b = pd.DataFrame(dong)
    sai = b["yhat"] - b["y"]
    rmse, rmse_nen = float(np.sqrt((sai ** 2).mean())), float(np.sqrt(((b["nen"] - b["y"]) ** 2).mean()))
    kq = {"so_ngay": len(b), "tu": b["ngay"].iloc[0], "den": b["ngay"].iloc[-1],
          "MAE": round(float(sai.abs().mean()), 2), "RMSE": round(rmse, 2), "bias": round(float(sai.mean()), 2),
          "ky_nang_so_voi_hom_qua": round(1 - rmse / rmse_nen, 3) if rmse_nen else None,
          "PICP_80": round(float(((b["y"] >= b["L"]) & (b["y"] <= b["U"])).mean()), 3), "xac_suat": {}}
    for k, t in NGUONG.items():
        o = (b["y"] > t).astype(float)
        p = b[f"p_{k}"]
        ti_le = float(o.mean())
        brier, brier_kh = float(((p - o) ** 2).mean()), float(((ti_le - o) ** 2).mean())
        bins = pd.cut(p, [0, .2, .4, .6, .8, 1.0001], include_lowest=True)
        tin_cay = [{"khoang": str(iv), "so_ngay": int(len(g)), "p_tb": round(float(g[f"p_{k}"].mean()), 3), "tan_suat_thuc": round(float((g["y"] > t).mean()), 3)}
                   for iv, g in b.groupby(bins, observed=True) if len(g)]
        kq["xac_suat"][k] = {"nguong": t, "ti_le_vuot_thuc_te": round(ti_le, 3), "Brier": round(brier, 4),
                             "Brier_khi_hau": round(brier_kh, 4), "BSS": round(1 - brier / brier_kh, 3) if brier_kh > 0 else None,
                             "do_tin_cay": tin_cay}
    kq["luu_y"] = (f"Kiểm chứng trên {len(b)} ngày sau mốc huấn luyện — mẫu nhỏ, chỉ số dao động lớn; cần cập nhật khi có thêm dữ liệu. "
                   "BSS > 0: xác suất dự báo tốt hơn dùng tần suất vượt thực tế cố định. Khi tỉ lệ vượt thực tế bằng 0 hoặc 1, Brier khí hậu = 0 "
                   "nên BSS không xác định. Xác suất tính từ giả định sai số phân phối chuẩn (predict.xac_suat_vuot).")
    return kq


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    model, meta = pr.load_model()
    mot = pd.Timestamp(meta["data_range"].split(" - ")[1]) + pd.Timedelta(days=1)
    df = pr._doc_chuoi_pm25(so_ngay=400)
    kq = danh_gia(df, model, meta, mot)
    kq["cap_nhat"] = datetime.now().isoformat(timespec="seconds")
    kq["mo_hinh_huan_luyen_den"] = str((mot - pd.Timedelta(days=1)).date())
    ra = GOC / "models" / "danh_gia_xac_suat.json"
    ra.write_text(json.dumps(kq, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in kq.items() if k != "xac_suat"}, ensure_ascii=False))
    for k, v in kq.get("xac_suat", {}).items():
        print(k, {x: v[x] for x in ("ti_le_vuot_thuc_te", "Brier", "Brier_khi_hau", "BSS")})
    print("Đã ghi", ra.relative_to(GOC))


if __name__ == "__main__":
    main()
