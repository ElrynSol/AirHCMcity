"""Nạp ranh giới 168 phường/xã/đặc khu của TP.HCM (sau sáp nhập 2025) vào PostGIS — bảng `phuong_xa`.

Nguồn: kho mở thanglequoc/vietnamese-provinces-database (GeoJSON theo Cục Đo đạc – Bản đồ, `diaphanhanhchinhcapxa_2025`).
    python data_pipeline/nap_ranh_gioi.py                 # dùng bản gọn có sẵn du_lieu/ranh_gioi/phuong_xa_hcm.geojson
    python data_pipeline/nap_ranh_gioi.py --tai-lai       # tải lại 168 tệp gốc từ GitHub rồi làm gọn
    python data_pipeline/nap_ranh_gioi.py --tu-thu-muc D  # làm gọn từ thư mục chứa các tệp *.geojson gốc

Làm gọn: sửa hình học lỗi (make_valid), đơn giản hóa ~30 m (giữ topology), làm tròn tọa độ 5 chữ số (~1 m) → 19 MB còn ~1 MB.
Trong CSDL: cột geom MultiPolygon SRID 4326 + chỉ mục GiST; cột khu_vuc theo tỉnh cũ trước sáp nhập
(mã phường < 26500: Bình Dương cũ; 26500–26733: Bà Rịa – Vũng Tàu cũ; ≥ 26734: TP.HCM cũ).
Máy chủ tự gọi nap_neu_trong() khi khởi động nên cài máy mới không cần chạy tay.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent
TEP_GON = GOC / "du_lieu" / "ranh_gioi" / "phuong_xa_hcm.geojson"
NGUON = "https://api.github.com/repos/thanglequoc/vietnamese-provinces-database/contents/json/geojson/79_ho_chi_minh/wards"
DO_GON = 0.0003   # độ (~30 m)

DDL = [
    """CREATE TABLE IF NOT EXISTS phuong_xa (
        ma VARCHAR(10) PRIMARY KEY,
        ten VARCHAR(100) NOT NULL,
        ten_day_du VARCHAR(150) NOT NULL,
        loai VARCHAR(20) NOT NULL,
        khu_vuc VARCHAR(40) NOT NULL,
        dien_tich_km2 DOUBLE PRECISION,
        geom geometry(MultiPolygon, 4326) NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS ix_phuong_xa_geom ON phuong_xa USING GIST (geom)",
    # Chỉ mục không gian cho các bảng điểm khác — dùng cho truy vấn trạm gần nhất (KNN), trong bán kính
    "CREATE INDEX IF NOT EXISTS ix_tram_toado ON tram_quan_trac USING GIST (toado)",
]


def khu_vuc(ma: str) -> str:
    m = int(ma)
    return "Bình Dương cũ" if m < 26500 else "Bà Rịa – Vũng Tàu cũ" if m < 26734 else "TP.HCM cũ"


def _tron(o):
    if isinstance(o, float):
        return round(o, 5)
    if isinstance(o, (list, tuple)):
        return [_tron(x) for x in o]
    return o


def lam_gon(cac_tep: list[Path]) -> dict:
    from shapely.geometry import MultiPolygon, mapping, shape
    from shapely.validation import make_valid
    dac = []
    for p in sorted(cac_tep):
        d = json.loads(p.read_text(encoding="utf-8"))
        f = d["features"][0] if d.get("type") == "FeatureCollection" else d
        pr = f["properties"]
        g = make_valid(shape(f["geometry"])).simplify(DO_GON, preserve_topology=True)
        if g.geom_type == "Polygon":
            g = MultiPolygon([g])
        elif g.geom_type == "GeometryCollection":
            g = MultiPolygon([x for x in g.geoms if x.geom_type == "Polygon"] +
                             [y for x in g.geoms if x.geom_type == "MultiPolygon" for y in x.geoms])
        ten_day = pr.get("fullName") or pr["name"]
        dac.append({"type": "Feature", "geometry": _tron(mapping(g)), "properties": {
            "ma": str(pr["code"]), "ten": pr["name"], "ten_day_du": ten_day,
            "loai": "Đặc khu" if ten_day.startswith("Đặc khu") else "Xã" if ten_day.startswith("Xã") else "Phường",
            "khu_vuc": khu_vuc(pr["code"]), "dien_tich_km2": pr.get("areaKm2")}})
    return {"type": "FeatureCollection", "nguon": "thanglequoc/vietnamese-provinces-database (diaphanhanhchinhcapxa_2025)",
            "features": dac}


def tai_ve(thu_muc: Path) -> list[Path]:
    import requests
    thu_muc.mkdir(parents=True, exist_ok=True)
    ds = requests.get(NGUON, timeout=30, headers={"User-Agent": "airhcm"}).json()
    ra = []
    for f in ds:
        p = thu_muc / f["name"]
        if not p.exists():
            p.write_bytes(requests.get(f["download_url"], timeout=60).content)
        ra.append(p)
    return ra


def nap_vao_csdl(fc: dict, engine) -> int:
    from sqlalchemy import text
    with engine.begin() as c:
        for cau in DDL:
            c.execute(text(cau))
        for f in fc["features"]:
            p = f["properties"]
            c.execute(text("""
                INSERT INTO phuong_xa (ma, ten, ten_day_du, loai, khu_vuc, dien_tich_km2, geom)
                VALUES (:ma, :ten, :ten_day_du, :loai, :khu_vuc, :dt,
                        ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(:g), 4326)), 3)))
                ON CONFLICT (ma) DO UPDATE SET ten = EXCLUDED.ten, ten_day_du = EXCLUDED.ten_day_du, loai = EXCLUDED.loai,
                    khu_vuc = EXCLUDED.khu_vuc, dien_tich_km2 = EXCLUDED.dien_tich_km2, geom = EXCLUDED.geom
            """), {**p, "dt": p.get("dien_tich_km2"), "g": json.dumps(f["geometry"])})
        return c.execute(text("SELECT count(*) FROM phuong_xa")).scalar()


def nap_neu_trong(engine) -> int | None:
    """Gọi khi máy chủ khởi động: bảng phuong_xa trống mà có tệp gọn thì nạp. Trả số phường đã nạp hoặc None."""
    from sqlalchemy import text
    with engine.begin() as c:
        for cau in DDL:
            c.execute(text(cau))
        if c.execute(text("SELECT count(*) FROM phuong_xa")).scalar() > 0 or not TEP_GON.exists():
            return None
    return nap_vao_csdl(json.loads(TEP_GON.read_text(encoding="utf-8")), engine)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tai-lai", action="store_true")
    ap.add_argument("--tu-thu-muc")
    a = ap.parse_args()
    if a.tu_thu_muc or a.tai_lai:
        tep = sorted(Path(a.tu_thu_muc).glob("*.geojson")) if a.tu_thu_muc else tai_ve(GOC / "du_lieu" / "ranh_gioi" / "goc")
        fc = lam_gon(tep)
        TEP_GON.parent.mkdir(parents=True, exist_ok=True)
        TEP_GON.write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"Đã làm gọn {len(fc['features'])} phường/xã → {TEP_GON.relative_to(GOC)} ({TEP_GON.stat().st_size / 1e6:.2f} MB)")
    sys.path.insert(0, str(GOC / "data_pipeline"))
    from db_url import get_engine
    n = nap_vao_csdl(json.loads(TEP_GON.read_text(encoding="utf-8")), get_engine())
    print(f"Đã nạp {n} phường/xã vào bảng phuong_xa (PostGIS, chỉ mục GiST)")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
