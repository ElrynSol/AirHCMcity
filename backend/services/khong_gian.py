"""Quét không gian bằng PostGIS: tìm trạm, thiết bị IoT, phản ánh, phường/xã trong vùng tròn / khung chữ nhật / đa giác.

Mọi phép đo làm trong CSDL trên kiểu geography (mặt cầu WGS84, đơn vị mét):
- Vùng tròn: ST_DWithin(điểm::geography, tâm::geography, bán kính) — dùng chỉ mục, chính xác theo mét.
- Khung / đa giác: ST_Intersects(geom, vùng) — dùng chỉ mục GiST.
- Khoảng cách tới "cột mốc" (vị trí người dùng hoặc tâm vùng): ST_Distance(geography).
- Phường/xã bị vùng quét cắt qua: tỉ lệ diện tích giao = ST_Area(ST_Intersection) / ST_Area(phường).
Kiểm tra "xung đột" hình học trước khi quét: đa giác tự cắt, quá ít điểm, quá rộng, nằm ngoài TP.HCM.
"""

from __future__ import annotations

import json

from sqlalchemy import text

from database import engine

BAN_KINH_MIN, BAN_KINH_MAX = 50, 50_000          # mét
DIEN_TICH_MAX_KM2 = 5_000                         # chặn quét vùng quá rộng (tốn tài nguyên, vô nghĩa)
SO_DINH_MAX = 200
VUNG_LAM_VIEC = (10.2, 11.6, 106.2, 107.6)        # lat0, lat1, lon0, lon1: TP.HCM sau sáp nhập + phụ cận


class LoiHinhHoc(ValueError):
    """Vùng quét không hợp lệ; `chi_tiet` mô tả xung đột (vd. vị trí điểm tự cắt) để giao diện đánh dấu."""

    def __init__(self, thong_diep, chi_tiet=None):
        super().__init__(thong_diep)
        self.chi_tiet = chi_tiet or {}


def _diem_hop_le(lat, lon, ten="Tọa độ"):
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        raise LoiHinhHoc(f"{ten} không phải số")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise LoiHinhHoc(f"{ten} ngoài phạm vi trái đất")
    a, b, c, d = VUNG_LAM_VIEC
    if not (a <= lat <= b and c <= lon <= d):
        raise LoiHinhHoc(f"{ten} ({lat:.4f}, {lon:.4f}) nằm ngoài khu vực TP.HCM mà hệ thống có dữ liệu")
    return lat, lon


def tao_vung(yc: dict) -> tuple[str, dict]:
    """Từ yêu cầu {kieu, tam, ban_kinh_m, dinh} tạo (GeoJSON vùng quét, thông tin). Ném LoiHinhHoc nếu sai."""
    kieu = yc.get("kieu")
    if kieu == "tron":
        lat, lon = _diem_hop_le((yc.get("tam") or {}).get("lat"), (yc.get("tam") or {}).get("lon"), "Tâm vòng tròn")
        try:
            r = float(yc.get("ban_kinh_m"))
        except (TypeError, ValueError):
            raise LoiHinhHoc("Bán kính không hợp lệ")
        if not BAN_KINH_MIN <= r <= BAN_KINH_MAX:
            raise LoiHinhHoc(f"Bán kính phải từ {BAN_KINH_MIN} m đến {BAN_KINH_MAX // 1000} km")
        return json.dumps({"type": "Point", "coordinates": [lon, lat]}), {"kieu": "tron", "tam": {"lat": lat, "lon": lon}, "ban_kinh_m": r}
    if kieu in ("khung", "da_giac"):
        dinh = yc.get("dinh") or []
        if len(dinh) < (2 if kieu == "khung" else 3):
            raise LoiHinhHoc("Đa giác cần ít nhất 3 điểm" if kieu == "da_giac" else "Khung cần 2 góc đối diện")
        if len(dinh) > SO_DINH_MAX:
            raise LoiHinhHoc(f"Đa giác tối đa {SO_DINH_MAX} điểm")
        pts = [_diem_hop_le(p.get("lat"), p.get("lon"), f"Điểm {i + 1}") for i, p in enumerate(dinh)]
        if kieu == "khung":
            la = [p[0] for p in pts]; lo = [p[1] for p in pts]
            if max(la) - min(la) < 1e-5 or max(lo) - min(lo) < 1e-5:
                raise LoiHinhHoc("Khung quá hẹp (hai góc trùng nhau)")
            pts = [(min(la), min(lo)), (min(la), max(lo)), (max(la), max(lo)), (max(la), min(lo))]
        vong = [[p[1], p[0]] for p in pts]
        vong.append(vong[0])
        return json.dumps({"type": "Polygon", "coordinates": [vong]}), {"kieu": kieu, "so_dinh": len(pts)}
    raise LoiHinhHoc("Kiểu vùng phải là: tron, khung hoặc da_giac")


def kiem_tra(c, gj: str, tt: dict, tu_sua: bool) -> str:
    """Kiểm tra xung đột hình học bằng PostGIS. Trả biểu thức SQL tạo vùng (đã sửa nếu tu_sua)."""
    if tt["kieu"] == "tron":
        return "ST_SetSRID(ST_GeomFromGeoJSON(:gj), 4326)"
    r = c.execute(text("""
        WITH g AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(:gj), 4326) AS g)
        SELECT ST_IsValid(g) AS hop_le, ST_IsValidReason(g) AS ly_do,
               ST_AsGeoJSON((ST_IsValidDetail(g)).location) AS vi_tri,
               ST_Area(ST_MakeValid(g)::geography) / 1e6 AS km2 FROM g
    """), {"gj": gj}).fetchone()
    if not r.hop_le and not tu_sua:
        vt = json.loads(r.vi_tri) if r.vi_tri else None
        raise LoiHinhHoc("Đa giác tự cắt (các cạnh giao nhau) nên không xác định được phần bên trong. "
                         "Hãy kéo các điểm để các cạnh không chéo nhau, hoặc bật “Tự sửa vùng”.",
                         {"loai": "tu_cat", "ly_do_postgis": r.ly_do,
                          "vi_tri": {"lat": vt["coordinates"][1], "lon": vt["coordinates"][0]} if vt else None})
    if r.km2 is None or r.km2 <= 0:
        raise LoiHinhHoc("Vùng có diện tích bằng 0")
    if r.km2 > DIEN_TICH_MAX_KM2:
        raise LoiHinhHoc(f"Vùng quá rộng ({r.km2:,.0f} km² > {DIEN_TICH_MAX_KM2:,} km²). Hãy thu nhỏ vùng quét.")
    tt["da_tu_sua"] = not r.hop_le
    return ("ST_CollectionExtract(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(:gj), 4326)), 3)"
            if not r.hop_le else "ST_SetSRID(ST_GeomFromGeoJSON(:gj), 4326)")


def quet(yc: dict) -> dict:
    gj, tt = tao_vung(yc)
    moc = yc.get("cot_moc")   # vị trí người dùng (kéo được) để đo khoảng cách; mặc định là tâm vùng
    with engine.connect() as c:
        bt = kiem_tra(c, gj, tt, bool(yc.get("tu_sua")))
        if tt["kieu"] == "tron":
            dk = "ST_DWithin({col}::geography, (SELECT g FROM vung)::geography, :r)"
            tam_sql = "(SELECT g FROM vung)"
        else:
            dk = "ST_Intersects({col}, (SELECT g FROM vung))"
            tam_sql = "(SELECT ST_PointOnSurface(g) FROM vung)"
        if moc and moc.get("lat") is not None:
            mlat, mlon = _diem_hop_le(moc.get("lat"), moc.get("lon"), "Cột mốc")
            moc_sql = "ST_SetSRID(ST_MakePoint(:mlon, :mlat), 4326)"
        else:
            mlat = mlon = None
            moc_sql = tam_sql
        ts = {"gj": gj, "r": tt.get("ban_kinh_m"), "mlat": mlat, "mlon": mlon}
        vung_cte = f"WITH vung AS (SELECT {bt} AS g), moc AS (SELECT {moc_sql} AS p)"

        thong_tin = c.execute(text(vung_cte + """
            SELECT CASE WHEN :r IS NULL THEN ST_Area((SELECT g FROM vung)::geography) / 1e6
                        ELSE pi() * :r * :r / 1e6 END AS km2,
                   ST_Y((SELECT p FROM moc)) AS mlat, ST_X((SELECT p FROM moc)) AS mlon,
                   ST_AsGeoJSON((SELECT g FROM vung), 6) AS vung_gj,
                   EXISTS (SELECT 1 FROM phuong_xa px WHERE """ + dk.format(col="px.geom") + """) AS trong_tp
        """), ts).fetchone()

        tram = c.execute(text(vung_cte + """,
            moi AS (SELECT DISTINCT ON (tram_id) tram_id, ngay_do, pm25_mean, pm10_mean, o3_mean
                    FROM du_lieu_tram_mat_dat ORDER BY tram_id, ngay_do DESC)
            SELECT t.id, t.ma_tram, t.ten_tram, ST_Y(t.toado) lat, ST_X(t.toado) lon,
                   ST_Distance(t.toado::geography, (SELECT p FROM moc)::geography) AS m,
                   m2.ngay_do, m2.pm25_mean, m2.pm10_mean, m2.o3_mean
            FROM tram_quan_trac t LEFT JOIN moi m2 ON m2.tram_id = t.id
            WHERE t.toado IS NOT NULL AND """ + dk.format(col="t.toado") + " ORDER BY m"), ts).fetchall()

        iot = c.execute(text(vung_cte + """
            SELECT t.ma, t.ten, ST_Y(t.toado) lat, ST_X(t.toado) lon,
                   ST_Distance(t.toado::geography, (SELECT p FROM moc)::geography) AS m
            FROM thiet_bi_iot t WHERE t.toado IS NOT NULL AND """ + dk.format(col="t.toado") + " ORDER BY m"), ts).fetchall()

        pa = c.execute(text(vung_cte + """
            SELECT p.id, p.loai, p.trang_thai, p.tao_luc, p.vi_do lat, p.kinh_do lon,
                   ST_Distance(ST_SetSRID(ST_MakePoint(p.kinh_do, p.vi_do), 4326)::geography, (SELECT p FROM moc)::geography) AS m
            FROM phan_anh p
            WHERE p.trang_thai <> 'an' AND p.tao_luc > NOW() - INTERVAL '7 days'
              AND """ + dk.format(col="ST_SetSRID(ST_MakePoint(p.kinh_do, p.vi_do), 4326)") + " ORDER BY m LIMIT 200"), ts).fetchall()

        # Phường/xã bị cắt: tỉ lệ diện tích nằm trong vùng quét (vùng tròn đổi thành đa giác trên mặt cầu bằng ST_Buffer geography)
        vung_dt = "(SELECT g FROM vung)" if tt["kieu"] != "tron" else "(SELECT ST_Buffer(g::geography, :r)::geometry FROM vung)"
        phuong = c.execute(text(vung_cte + f"""
            SELECT px.ma, px.ten_day_du, px.khu_vuc,
                   ST_Area(ST_Intersection(px.geom, {vung_dt})::geography) / NULLIF(ST_Area(px.geom::geography), 0) AS ti_le,
                   ST_Distance(ST_PointOnSurface(px.geom)::geography, (SELECT p FROM moc)::geography) AS m
            FROM phuong_xa px WHERE ST_Intersects(px.geom, {vung_dt})
            ORDER BY ti_le DESC NULLS LAST LIMIT 100"""), ts).fetchall()

    from tinh_aqi import muc_aqi, tinh_aqi_tong_hop
    ds_tram = []
    for t in tram:
        aqi, chat = tinh_aqi_tong_hop(pm25=t.pm25_mean, pm10=t.pm10_mean, o3=t.o3_mean)
        m = muc_aqi(aqi) or {}
        ds_tram.append({"id": t.id, "ma": t.ma_tram, "ten": t.ten_tram, "lat": t.lat, "lon": t.lon, "km": round(t.m / 1000, 2),
                        "ngay": str(t.ngay_do) if t.ngay_do else None, "pm25": round(t.pm25_mean, 1) if t.pm25_mean is not None else None,
                        "aqi": aqi, "chat": chat, "muc": m.get("muc"), "mau": m.get("mau")})
    aqi_ds = [x["aqi"] for x in ds_tram if x["aqi"] is not None]
    from services import phan_anh as pa_sv
    return {
        "vung": {**tt, "dien_tich_km2": round(thong_tin.km2, 3), "geojson": json.loads(thong_tin.vung_gj), "trong_tp": thong_tin.trong_tp},
        "cot_moc": {"lat": thong_tin.mlat, "lon": thong_tin.mlon, "la_vi_tri_nguoi_dung": mlat is not None},
        "tram": ds_tram,
        "iot": [{"ma": r.ma, "ten": r.ten, "lat": r.lat, "lon": r.lon, "km": round(r.m / 1000, 2)} for r in iot],
        "phan_anh": [{"id": r.id, "loai": r.loai, "ten_loai": pa_sv.LOAI.get(r.loai, pa_sv.LOAI["khac"])["ten"],
                      "bieu_tuong": pa_sv.LOAI.get(r.loai, pa_sv.LOAI["khac"])["bt"], "trang_thai": r.trang_thai,
                      "tao_luc": r.tao_luc.isoformat(), "lat": r.lat, "lon": r.lon, "km": round(r.m / 1000, 2)} for r in pa],
        "phuong": [{"ma": r.ma, "ten": r.ten_day_du, "khu_vuc": r.khu_vuc, "ti_le_trong_vung": round(float(r.ti_le or 0), 3),
                    "km": round(r.m / 1000, 2)} for r in phuong],
        "tom_tat": {"so_tram": len(ds_tram), "so_iot": len(iot), "so_phan_anh": len(pa), "so_phuong": len(phuong),
                    "aqi_tb": round(sum(aqi_ds) / len(aqi_ds)) if aqi_ds else None, "aqi_cao_nhat": max(aqi_ds) if aqi_ds else None},
    }


def tram_gan_nhat(lat: float, lon: float, so: int = 3) -> list[dict]:
    """K trạm gần nhất (KNN `<->` dùng chỉ mục GiST) và khoảng cách đường chim bay."""
    lat, lon = _diem_hop_le(lat, lon, "Vị trí")
    with engine.connect() as c:
        rows = c.execute(text("""
            SELECT ma_tram, ten_tram, ST_Y(toado) lat, ST_X(toado) lon,
                   ST_Distance(toado::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) m
            FROM tram_quan_trac WHERE toado IS NOT NULL
            ORDER BY toado <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) LIMIT :k"""), {"lat": lat, "lon": lon, "k": so}).fetchall()
    return [{"ma": r.ma_tram, "ten": r.ten_tram, "lat": r.lat, "lon": r.lon, "km": round(r.m / 1000, 2)} for r in rows]
