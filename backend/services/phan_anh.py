"""Phản ánh ô nhiễm từ người dân (khói, đốt rác, bụi công trình, mùi hôi...) hiển thị trên bản đồ.

Ý tưởng theo Pham-Quoc và cs. (2021), "Air Quality Monitoring Systems with Multiple Data Sources for Ho Chi Minh City"
(EAI Endorsed Trans. Context-aware Systems and Applications): ngoài cảm biến và ảnh vệ tinh, hệ thống nhận thêm cảnh báo
do người dân gửi — nguồn thông tin tại chỗ mà số liệu mô hình lưới ~45 km không thấy được.

Quy tắc:
- Phải đăng nhập mới gửi được (chống spam); tối đa 5 phản ánh/giờ mỗi tài khoản.
- Phản ánh mới hiện ngay trên bản đồ ở trạng thái "chưa xác minh" và CHỈ hiện loại + thời điểm + vị trí;
  phần mô tả tự do chỉ công khai sau khi quản trị viên xác minh (tránh phát tán nội dung xấu).
- Người dùng khác bấm "Tôi cũng thấy" để tăng độ tin cậy. Phản ánh tự ẩn khỏi bản đồ sau 72 giờ.
- Lưu kèm AQI toàn thành phố lúc gửi để sau này đối chiếu phản ánh với số liệu.
"""

from __future__ import annotations

from sqlalchemy import text

from database import engine

LOAI = {
    "khoi": {"ten": "Khói", "bt": "💨"},
    "dot_rac": {"ten": "Đốt rác / đốt rơm rạ", "bt": "🔥"},
    "bui_cong_trinh": {"ten": "Bụi công trình", "bt": "🏗️"},
    "khi_thai_xe": {"ten": "Khí thải xe cộ", "bt": "🚚"},
    "khi_thai_nha_may": {"ten": "Khí thải nhà máy", "bt": "🏭"},
    "mui_hoi": {"ten": "Mùi hôi / hóa chất", "bt": "🤢"},
    "khac": {"ten": "Khác", "bt": "❗"},
}
TRANG_THAI = ("moi", "xac_minh", "an")
# Phạm vi nhận phản ánh: TP.HCM và vùng phụ cận mà bản đồ của hệ thống bao phủ
VI_DO = (10.2, 11.6)
KINH_DO = (106.2, 107.6)
MO_TA_TOI_DA = 500
GIO_HIEN_MAC_DINH = 72
GIO_HIEN_TOI_DA = 24 * 7

DDL = [
    """CREATE TABLE IF NOT EXISTS phan_anh (
        id SERIAL PRIMARY KEY,
        nguoi_dung_id INTEGER REFERENCES nguoi_dung(id) ON DELETE SET NULL,
        loai VARCHAR(30) NOT NULL,
        mo_ta VARCHAR(500),
        vi_do DOUBLE PRECISION NOT NULL,
        kinh_do DOUBLE PRECISION NOT NULL,
        aqi_tp INTEGER,
        trang_thai VARCHAR(12) NOT NULL DEFAULT 'moi',
        tao_luc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        duyet_boi INTEGER REFERENCES nguoi_dung(id) ON DELETE SET NULL,
        duyet_luc TIMESTAMPTZ)""",
    "CREATE INDEX IF NOT EXISTS ix_phan_anh_tao_luc ON phan_anh (tao_luc DESC)",
    """CREATE TABLE IF NOT EXISTS phan_anh_xac_nhan (
        phan_anh_id INTEGER NOT NULL REFERENCES phan_anh(id) ON DELETE CASCADE,
        nguoi_dung_id INTEGER NOT NULL REFERENCES nguoi_dung(id) ON DELETE CASCADE,
        tao_luc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (phan_anh_id, nguoi_dung_id))""",
]


def tao_bang():
    with engine.begin() as c:
        for cau in DDL:
            c.execute(text(cau))


def chuan_hoa(loai: str, mo_ta: str | None, vi_do: float, kinh_do: float) -> dict:
    """Kiểm tra và làm sạch dữ liệu gửi lên. Sai thì ném ValueError kèm thông báo tiếng Việt."""
    if loai not in LOAI:
        raise ValueError("Loại phản ánh không hợp lệ")
    try:
        vi_do, kinh_do = float(vi_do), float(kinh_do)
    except (TypeError, ValueError):
        raise ValueError("Tọa độ không hợp lệ")
    if not (VI_DO[0] <= vi_do <= VI_DO[1] and KINH_DO[0] <= kinh_do <= KINH_DO[1]):
        raise ValueError("Vị trí nằm ngoài khu vực TP.HCM mà hệ thống theo dõi")
    mo_ta = " ".join((mo_ta or "").split())          # gộp khoảng trắng, bỏ xuống dòng thừa
    if len(mo_ta) > MO_TA_TOI_DA:
        raise ValueError(f"Mô tả tối đa {MO_TA_TOI_DA} ký tự")
    if loai == "khac" and len(mo_ta) < 10:
        raise ValueError("Với loại “Khác”, hãy mô tả ít nhất 10 ký tự")
    return {"loai": loai, "mo_ta": mo_ta or None, "vi_do": round(vi_do, 6), "kinh_do": round(kinh_do, 6)}


def _aqi_tp() -> int | None:
    try:
        from services.tong_quan import tong_quan
        v = ((tong_quan() or {}).get("hien_tai") or {}).get("aqi")
        return int(v) if v is not None else None
    except Exception:
        return None


def them(nguoi_dung_id: int, du_lieu: dict) -> int:
    with engine.begin() as c:
        return c.execute(text("""
            INSERT INTO phan_anh (nguoi_dung_id, loai, mo_ta, vi_do, kinh_do, aqi_tp)
            VALUES (:u, :loai, :mo_ta, :vi_do, :kinh_do, :aqi) RETURNING id
        """), {"u": nguoi_dung_id, **du_lieu, "aqi": _aqi_tp()}).scalar()


def _dong(r, nguoi_xem: int | None, admin: bool = False) -> dict:
    cua_toi = nguoi_xem is not None and r.nguoi_dung_id == nguoi_xem
    d = {"id": r.id, "loai": r.loai, "ten_loai": LOAI.get(r.loai, LOAI["khac"])["ten"], "bieu_tuong": LOAI.get(r.loai, LOAI["khac"])["bt"],
         "vi_do": r.vi_do, "kinh_do": r.kinh_do, "tao_luc": r.tao_luc.isoformat(), "trang_thai": r.trang_thai,
         "aqi_tp": r.aqi_tp, "so_xac_nhan": r.so_xac_nhan, "phuong": r.phuong, "cua_toi": cua_toi, "da_xac_nhan": bool(r.da_xac_nhan),
         # Mô tả tự do: chỉ công khai khi đã xác minh; người gửi và admin luôn thấy
         "mo_ta": r.mo_ta if (r.trang_thai == "xac_minh" or cua_toi or admin) else None}
    if admin:
        d["nguoi_gui"] = r.email
    return d


_CHON = """
    SELECT p.*, u.email,
           (SELECT px.ten_day_du FROM phuong_xa px   -- PostGIS: phường/xã chứa điểm phản ánh (chỉ mục GiST)
             WHERE ST_Contains(px.geom, ST_SetSRID(ST_MakePoint(p.kinh_do, p.vi_do), 4326)) LIMIT 1) AS phuong,
           (SELECT count(*) FROM phan_anh_xac_nhan x WHERE x.phan_anh_id = p.id) AS so_xac_nhan,
           EXISTS (SELECT 1 FROM phan_anh_xac_nhan x WHERE x.phan_anh_id = p.id AND x.nguoi_dung_id = :xem) AS da_xac_nhan
    FROM phan_anh p LEFT JOIN nguoi_dung u ON u.id = p.nguoi_dung_id
"""


def ds_cong_khai(gio: int, nguoi_xem: int | None) -> list[dict]:
    gio = max(1, min(int(gio), GIO_HIEN_TOI_DA))
    with engine.connect() as c:
        rows = c.execute(text(_CHON + """
            WHERE p.trang_thai <> 'an' AND p.tao_luc > NOW() - make_interval(hours => :g)
            ORDER BY p.tao_luc DESC LIMIT 500
        """), {"g": gio, "xem": nguoi_xem or 0}).fetchall()
    return [_dong(r, nguoi_xem) for r in rows]


def ds_cua_toi(nguoi_dung_id: int) -> list[dict]:
    with engine.connect() as c:
        rows = c.execute(text(_CHON + " WHERE p.nguoi_dung_id = :u ORDER BY p.tao_luc DESC LIMIT 100"),
                         {"u": nguoi_dung_id, "xem": nguoi_dung_id}).fetchall()
    return [_dong(r, nguoi_dung_id) for r in rows]


def ds_quan_tri(ngay: int = 30) -> list[dict]:
    with engine.connect() as c:
        rows = c.execute(text(_CHON + " WHERE p.tao_luc > NOW() - make_interval(days => :n) ORDER BY (p.trang_thai = 'moi') DESC, p.tao_luc DESC LIMIT 500"),
                         {"n": ngay, "xem": 0}).fetchall()
    return [_dong(r, None, admin=True) for r in rows]


def xac_nhan(phan_anh_id: int, nguoi_dung_id: int) -> str:
    """'Tôi cũng thấy'. Trả 'ok' | 'khong_co' | 'cua_minh' | 'da_co'."""
    with engine.begin() as c:
        r = c.execute(text("SELECT nguoi_dung_id, trang_thai FROM phan_anh WHERE id = :i"), {"i": phan_anh_id}).fetchone()
        if not r or r.trang_thai == "an":
            return "khong_co"
        if r.nguoi_dung_id == nguoi_dung_id:
            return "cua_minh"
        n = c.execute(text("INSERT INTO phan_anh_xac_nhan (phan_anh_id, nguoi_dung_id) VALUES (:i, :u) ON CONFLICT DO NOTHING"),
                      {"i": phan_anh_id, "u": nguoi_dung_id}).rowcount
    return "ok" if n else "da_co"


def xoa(phan_anh_id: int, nguoi_dung_id: int, admin: bool) -> bool:
    with engine.begin() as c:
        return bool(c.execute(text("DELETE FROM phan_anh WHERE id = :i AND (:a OR nguoi_dung_id = :u)"),
                              {"i": phan_anh_id, "u": nguoi_dung_id, "a": admin}).rowcount)


def duyet(phan_anh_id: int, trang_thai: str, admin_id: int) -> bool:
    if trang_thai not in TRANG_THAI:
        raise ValueError("Trạng thái không hợp lệ")
    with engine.begin() as c:
        return bool(c.execute(text("UPDATE phan_anh SET trang_thai = :t, duyet_boi = :a, duyet_luc = NOW() WHERE id = :i"),
                              {"t": trang_thai, "a": admin_id, "i": phan_anh_id}).rowcount)


def thong_ke(ngay: int = 30) -> dict:
    with engine.connect() as c:
        rows = c.execute(text("SELECT loai, count(*) n FROM phan_anh WHERE trang_thai <> 'an' AND tao_luc > NOW() - make_interval(days => :n) GROUP BY loai ORDER BY n DESC"),
                         {"n": ngay}).fetchall()
    return {"ngay": ngay, "tong": sum(r.n for r in rows),
            "theo_loai": [{"loai": r.loai, "ten": LOAI.get(r.loai, LOAI["khac"])["ten"], "bieu_tuong": LOAI.get(r.loai, LOAI["khac"])["bt"], "so": r.n} for r in rows]}
