"""Khảo sát mức độ dễ dùng theo thang SUS (System Usability Scale, Brooke 1996) — đánh giá AirHCM từ người dùng thật.

10 câu, mỗi câu 1–5 (1 = rất không đồng ý, 5 = rất đồng ý). Câu lẻ là ý tích cực, câu chẵn là ý tiêu cực.
Điểm SUS = 2,5 × [Σ(câu lẻ − 1) + Σ(5 − câu chẵn)], thang 0–100. Mốc tham chiếu (Bangor và cs. 2009; Sauro 2011):
trung bình các hệ thống ≈ 68; ≥ 80,3 thuộc nhóm tốt nhất (hạng A); < 51 là kém (hạng F).
Không lưu IP thô: chỉ lưu mã băm (SHA-256 có muối) để chống gửi trùng.
"""
from __future__ import annotations

import hashlib
import math
import os

from sqlalchemy import text

from database import engine

CAU_HOI = [
    "Tôi nghĩ tôi sẽ muốn dùng AirHCM thường xuyên.",
    "Tôi thấy AirHCM phức tạp một cách không cần thiết.",
    "Tôi thấy AirHCM dễ sử dụng.",
    "Tôi nghĩ tôi cần người có chuyên môn kỹ thuật hỗ trợ mới dùng được AirHCM.",
    "Tôi thấy các chức năng của AirHCM được kết nối với nhau hợp lý.",
    "Tôi thấy AirHCM có quá nhiều chỗ không nhất quán.",
    "Tôi nghĩ hầu hết mọi người sẽ học cách dùng AirHCM rất nhanh.",
    "Tôi thấy AirHCM rất rườm rà, khó thao tác.",
    "Tôi cảm thấy rất tự tin khi dùng AirHCM.",
    "Tôi phải học nhiều thứ trước khi dùng được AirHCM.",
]
VAI_TRO = {"nguoi_dan": "Người dân", "sinh_vien": "Sinh viên", "giang_vien": "Giảng viên / chuyên gia", "khac": "Khác"}
_da_tao = False


def tao_bang():
    global _da_tao
    if _da_tao:
        return
    with engine.begin() as c:
        c.execute(text("""CREATE TABLE IF NOT EXISTS khao_sat_sus (
            id SERIAL PRIMARY KEY, tao_luc TIMESTAMPTZ NOT NULL DEFAULT NOW(), vai_tro TEXT NOT NULL,
            tra_loi SMALLINT[] NOT NULL CHECK (array_length(tra_loi, 1) = 10), diem REAL NOT NULL,
            y_kien TEXT, ma_bam_ip TEXT)"""))
    _da_tao = True


def diem_sus(tra_loi: list[int]) -> float:
    if len(tra_loi) != 10 or any(not isinstance(x, int) or x < 1 or x > 5 for x in tra_loi):
        raise ValueError("Cần đủ 10 câu trả lời, mỗi câu từ 1 đến 5")
    return 2.5 * sum((x - 1) if i % 2 == 0 else (5 - x) for i, x in enumerate(tra_loi))


def xep_hang(diem: float) -> str:
    return ("A — rất tốt" if diem >= 80.3 else "B — tốt" if diem >= 74 else "C — trung bình" if diem >= 68
            else "D — dưới trung bình" if diem >= 51 else "F — kém")


def bam_ip(ip: str) -> str:
    muoi = os.getenv("JWT_SECRET_KEY", "airhcm")
    return hashlib.sha256(f"{muoi}|{ip}".encode()).hexdigest()[:32]


def them(vai_tro: str, tra_loi: list[int], y_kien: str | None, ip: str) -> float:
    if vai_tro not in VAI_TRO:
        raise ValueError("Vai trò không hợp lệ")
    d = diem_sus(tra_loi)
    tao_bang()
    with engine.begin() as c:
        c.execute(text("INSERT INTO khao_sat_sus (vai_tro, tra_loi, diem, y_kien, ma_bam_ip) VALUES (:v, :t, :d, :y, :h)"),
                  {"v": vai_tro, "t": tra_loi, "d": d, "y": (y_kien or "").strip()[:500] or None, "h": bam_ip(ip)})
    return d


def tong_hop_tu(dong: list[tuple]) -> dict:
    """dong: [(vai_tro, tra_loi[10], diem)]. Hàm thuần để kiểm thử."""
    n = len(dong)
    if n == 0:
        return {"so_phieu": 0}
    diem = [float(x[2]) for x in dong]
    tb = sum(diem) / n
    sd = math.sqrt(sum((x - tb) ** 2 for x in diem) / (n - 1)) if n > 1 else 0.0
    t = {2: 12.71, 3: 4.30, 4: 3.18, 5: 2.78, 6: 2.57, 8: 2.36, 10: 2.26, 15: 2.14, 20: 2.09, 30: 2.05}.get(n, 1.96 if n > 30 else 2.1)
    ci = t * sd / math.sqrt(n) if n > 1 else None
    theo_cau = [round(sum(x[1][i] for x in dong) / n, 2) for i in range(10)]
    theo_vai = {}
    for v, _, d in dong:
        theo_vai.setdefault(VAI_TRO.get(v, v), []).append(float(d))
    return {"so_phieu": n, "sus_tb": round(tb, 1), "do_lech_chuan": round(sd, 1),
            "ci95": None if ci is None else [round(tb - ci, 1), round(tb + ci, 1)], "xep_hang": xep_hang(tb),
            "theo_cau": [{"cau": CAU_HOI[i], "tb": theo_cau[i], "tich_cuc": i % 2 == 0} for i in range(10)],
            "theo_vai_tro": {k: {"so_phieu": len(v), "sus_tb": round(sum(v) / len(v), 1)} for k, v in theo_vai.items()},
            "phan_bo": {h: sum(1 for x in diem if xep_hang(x).startswith(h)) for h in "ABCDF"}}


def tong_hop() -> dict:
    tao_bang()
    with engine.connect() as c:
        dong = [(r.vai_tro, list(r.tra_loi), r.diem) for r in c.execute(text("SELECT vai_tro, tra_loi, diem FROM khao_sat_sus"))]
        y_kien = [r.y_kien for r in c.execute(text("SELECT y_kien FROM khao_sat_sus WHERE y_kien IS NOT NULL ORDER BY tao_luc DESC LIMIT 20"))]
    return {**tong_hop_tu(dong), "y_kien_gan_day": y_kien}
