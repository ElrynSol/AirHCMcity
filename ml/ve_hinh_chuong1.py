"""Vẽ lại Hình 1.1, 1.2, 1.3 của báo cáo đồ án trực tiếp từ CSDL PostgreSQL của hệ thống.

Chạy từ thư mục gốc dự án:   python ml/ve_hinh_chuong1.py
Ảnh ghi vào docs/hinh_bao_cao/. Script chỉ đọc CSDL, không sửa dữ liệu.

Hình 1.1  Diễn biến PM2.5 trung bình ngày tại TP.HCM (h_pm25_chuoi.png)
          - Bảng du_lieu_tram_mat_dat: mỗi ngày lấy trung bình cột pm25_mean của 17 điểm (số liệu CAMS qua Open-Meteo).
          - Đường đen mảnh: giá trị từng ngày; đường xám đậm: trung bình trượt 30 ngày (làm mượt để thấy xu hướng).
          - Ngưỡng QCVN 05:2023/BTNMT trung bình 24 giờ: 50 µg/m³ đến hết 2025, 45 µg/m³ từ 2026; WHO 2021: 15 µg/m³.
Hình 1.2  PM2.5 và tốc độ gió trung bình theo tháng (h_pm25_thang.png)
          - Cùng chuỗi ngày ở trên, gom theo tháng trong năm (1–12) rồi lấy trung bình PM2.5 (cột) và gió (đường nét đứt).
Hình 1.3  Vị trí 17 điểm ước tính và 3 điểm đo thật trên ranh giới 168 phường/xã (h_ban_do_diem.png)
          - Bảng phuong_xa (ranh giới, PostGIS), tram_quan_trac (17 điểm), tram_do_that (3 điểm OpenAQ).
"""
import json
import sys
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC / "backend"))
import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402
from sqlalchemy import text  # noqa: E402
from database import engine  # noqa: E402

RA = GOC / "docs" / "hinh_bao_cao"
RA.mkdir(parents=True, exist_ok=True)

# ---------- Hình 1.1 ----------
df = pd.read_sql("SELECT ngay_do, AVG(pm25_mean) AS pm25 FROM du_lieu_tram_mat_dat "
                 "WHERE pm25_mean IS NOT NULL GROUP BY ngay_do ORDER BY ngay_do", engine)
df["ngay_do"] = pd.to_datetime(df["ngay_do"])
s = df.set_index("ngay_do")["pm25"]
qcvn = pd.Series(s.index.map(lambda d: 45 if d.year >= 2026 else 50), index=s.index)
fig, ax = plt.subplots(figsize=(10, 4.2), dpi=150)
ax.plot(s.index, s.values, color="#4C9BE8", lw=0.7, label="PM2.5 trung bình ngày (CAMS, 17 điểm)")
ax.plot(s.rolling(30, center=True).mean(), color="#0B3C78", lw=2, label="Trung bình trượt 30 ngày")
ax.step(qcvn.index, qcvn.values, where="post", color="#D62728", ls="--", lw=1.4, label="QCVN 05:2023 (24 giờ)")
ax.axhline(15, color="#2CA02C", ls="--", lw=1.4, label="WHO 2021 (15 µg/m³)")
ax.set_ylabel("PM2.5 (µg/m³)"); ax.set_xlabel("Thời gian"); ax.grid(alpha=.3)
ax.legend(fontsize=8, loc="upper left", ncol=2); ax.set_ylim(0, max(60, s.max() + 5))
fig.tight_layout(); fig.savefig(RA / "h_pm25_chuoi.png"); plt.close(fig)
print(f"Hình 1.1: {len(s)} ngày ({s.index.min().date()} → {s.index.max().date()}), "
      f"trung bình {s.mean():.1f}, cao nhất {s.max():.1f} µg/m³ ngày {s.idxmax().date()}")

# ---------- Hình 1.2 ----------
df = pd.read_sql("SELECT ngay_do, AVG(pm25_mean) AS pm25, AVG(gio_toc_do_mean) AS gio "
                 "FROM du_lieu_tram_mat_dat GROUP BY ngay_do", engine)
df["th"] = pd.to_datetime(df["ngay_do"]).dt.month
m = df.groupby("th")[["pm25", "gio"]].mean()
fig, ax = plt.subplots(figsize=(9, 3.8), dpi=150)
ax.bar(m.index - 0.2, m["pm25"], width=0.4, color=["#E8833A" if v >= 25 else "#F2C14E" for v in m["pm25"]])
ax2 = ax.twinx(); ax2.plot(m.index, m["gio"], "--o", color="#1F77B4", ms=4, label="Tốc độ gió trung bình (km/h)")
ax.set_xticks(range(1, 13)); ax.set_xlabel("Tháng"); ax.set_ylabel("PM2.5 (µg/m³)"); ax2.set_ylabel("Gió (km/h)")
from matplotlib.patches import Patch
h1 = [Patch(color="#F2C14E", label="PM2.5 trung bình < 25 µg/m³"), Patch(color="#E8833A", label="PM2.5 trung bình ≥ 25 µg/m³")]; l1 = [h.get_label() for h in h1]
h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, fontsize=8, loc="upper left"); ax.grid(alpha=.2, axis="y")
fig.tight_layout(); fig.savefig(RA / "h_pm25_thang.png"); plt.close(fig)
print("Hình 1.2: trung bình theo tháng\n" + m.round(1).T.to_string())

# ---------- Hình 1.3 ----------
with engine.connect() as c:
    px = c.execute(text("SELECT ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, 0.0008)) g FROM phuong_xa")).fetchall()
    tram = c.execute(text("SELECT ma_tram, ST_Y(toado) lat, ST_X(toado) lon FROM tram_quan_trac ORDER BY ma_tram")).fetchall()
    that = c.execute(text("SELECT ST_Y(toado) lat, ST_X(toado) lon FROM tram_do_that")).fetchall()
polys = []
for r in px:
    g = json.loads(r.g)
    for poly in (g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]):
        polys.append(poly[0])
fig, ax = plt.subplots(figsize=(8.6, 7.2), dpi=150)
ax.add_collection(PolyCollection(polys, facecolors="#E6F2EC", edgecolors="#7A9A8A", linewidths=0.3))
for t in tram:
    ax.plot(t.lon, t.lat, "o", color="#1F77B4", mec="white", ms=6)
    ax.annotate(t.ma_tram, (t.lon, t.lat), xytext=(3, 3), textcoords="offset points", fontsize=7)
for t in that:
    ax.plot(t.lon, t.lat, "^", color="#D62728", mec="black", ms=9, mew=0.8)
ax.plot([], [], "o", color="#1F77B4", mec="white", ms=6, label=f"Điểm ước tính ({len(tram)} điểm)")
ax.plot([], [], "^", color="#D62728", mec="black", ms=9, mew=0.8, label=f"Điểm đo thật OpenAQ ({len(that)} điểm)")
ax.legend(loc="lower right", fontsize=8); ax.set_xlabel("Kinh độ"); ax.set_ylabel("Vĩ độ")
ax.set_xlim(106.33, 107.62); ax.set_ylim(10.30, 11.62); ax.set_aspect(1 / 0.982); ax.grid(alpha=.2)
ax.text(0.01, 0.01, "Không hiển thị đặc khu Côn Đảo (ở xa phía nam)", transform=ax.transAxes, fontsize=7, color="#555555")
fig.tight_layout(); fig.savefig(RA / "h_ban_do_diem.png"); plt.close(fig)
print(f"Hình 1.3: {len(polys)} vùng ranh giới, {len(tram)} điểm ước tính, {len(that)} điểm đo thật")
print(f"Đã lưu vào {RA}")
