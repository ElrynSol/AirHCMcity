"""API trạm cảm biến IoT mô phỏng (Wokwi): danh sách thiết bị, lịch sử đo, trạng thái MQTT, cảnh báo gần đây."""

from core import config  # noqa: F401
from fastapi import APIRouter
from sqlalchemy import text

from database import engine
from services import iot as iot_service
from tinh_aqi import muc_aqi

router = APIRouter()


@router.get("/api/v1/iot/trang-thai")
def trang_thai():
    t = dict(iot_service.trang_thai)
    t.update({"nguong_aqi": iot_service.NGUONG_AQI, "topic_tram": iot_service.TOPIC_TRAM, "topic_bang": iot_service.TOPIC_BANG,
              "gui_email": bool(iot_service.EMAIL_NHAN)})
    return t


@router.get("/api/v1/iot/thiet-bi")
def ds_thiet_bi():
    """Mỗi thiết bị: lần đo mới nhất, AQI (TB 1 phút), trạng thái trực tuyến (có tin trong 30 giây)."""
    out = []
    try:
        with engine.connect() as c:
            rows = c.execute(text("""
                SELECT t.ma, t.ten, t.vi_do, t.kinh_do, d.thoi_gian, d.pm25, d.pm10, d.nhiet_do, d.do_am, d.che_do,
                       EXTRACT(EPOCH FROM (NOW() - d.thoi_gian)) AS tuoi,
                       px.ten_day_du AS phuong, px.khu_vuc, g.ma_tram, g.km
                FROM thiet_bi_iot t
                LEFT JOIN LATERAL (SELECT * FROM du_lieu_iot WHERE ma_thiet_bi = t.ma ORDER BY thoi_gian DESC LIMIT 1) d ON TRUE
                LEFT JOIN phuong_xa px ON px.ma = t.ma_phuong
                LEFT JOIN LATERAL (   -- trạm quan trắc gần nhất: KNN trên chỉ mục GiST, khoảng cách thật trên mặt cầu
                    SELECT q.ma_tram, ST_Distance(t.toado::geography, q.toado::geography) / 1000.0 AS km
                    FROM tram_quan_trac q WHERE t.toado IS NOT NULL AND q.toado IS NOT NULL
                    ORDER BY q.toado <-> t.toado LIMIT 1) g ON TRUE
                ORDER BY t.ma""")).fetchall()
            for r in rows:
                aqi, chat, _ = iot_service.aqi_trung_binh_1_phut(c, r.ma)
                m = muc_aqi(aqi)
                out.append({"ma": r.ma, "ten": r.ten, "lat": r.vi_do, "lon": r.kinh_do, "mo_phong": True,
                            "thoi_gian": r.thoi_gian.strftime("%Y-%m-%d %H:%M:%S") if r.thoi_gian else None,
                            "tuoi_giay": int(r.tuoi) if r.tuoi is not None else None,
                            "truc_tuyen": r.tuoi is not None and r.tuoi < 30,
                            "pm25": r.pm25, "pm10": r.pm10, "nhiet_do": r.nhiet_do, "do_am": r.do_am, "che_do": r.che_do,
                            "aqi": aqi, "chat": chat, "muc": m["muc"] if m else None,
                            "phuong": r.phuong, "khu_vuc": r.khu_vuc, "tram_gan_nhat": r.ma_tram,
                            "km_tram_gan_nhat": round(r.km, 2) if r.km is not None else None})
    except Exception:
        return []   # bảng chưa tạo (IoT tắt hoặc chưa có thư viện MQTT)
    return out


@router.get("/api/v1/iot/{ma}/lich-su")
def lich_su(ma: str, phut: int = 30):
    phut = max(1, min(phut, 24 * 60))
    with engine.connect() as c:
        rows = c.execute(text("""
            SELECT thoi_gian, pm25, pm10, nhiet_do, do_am, aqi FROM du_lieu_iot
            WHERE ma_thiet_bi = :m AND thoi_gian > NOW() - make_interval(mins => :p) ORDER BY thoi_gian"""),
                         {"m": ma, "p": phut}).fetchall()
    return [{"t": r.thoi_gian.strftime("%H:%M:%S"), "pm25": r.pm25, "pm10": r.pm10, "nhiet_do": r.nhiet_do,
             "do_am": r.do_am, "aqi": r.aqi} for r in rows]


@router.get("/api/v1/iot/{ma}/theo-gio")
def theo_gio(ma: str, ngay: int = 7):
    """Số liệu tổng hợp theo giờ (giữ lâu dài, khác số đo thô chỉ giữ 7 ngày)."""
    ngay = max(1, min(ngay, 365))
    with engine.connect() as c:
        rows = c.execute(text("""
            SELECT gio, so_mau, pm25_tb, pm25_max, pm10_tb, nhiet_do_tb, do_am_tb, aqi_max FROM du_lieu_iot_gio
            WHERE ma_thiet_bi = :m AND gio > NOW() - make_interval(days => :n) ORDER BY gio"""), {"m": ma, "n": ngay}).fetchall()
    r2 = lambda x: None if x is None else round(float(x), 1)
    return [{"gio": r.gio.strftime("%Y-%m-%d %H:00"), "so_mau": r.so_mau, "pm25_tb": r2(r.pm25_tb), "pm25_max": r2(r.pm25_max),
             "pm10_tb": r2(r.pm10_tb), "nhiet_do_tb": r2(r.nhiet_do_tb), "do_am_tb": r2(r.do_am_tb), "aqi_max": r.aqi_max} for r in rows]


@router.get("/api/v1/iot/csdl")
def thong_ke_csdl():
    """Tình trạng lưu trữ IoT trong CSDL (để trình bày): số thiết bị, số đo thô, số giờ đã tổng hợp."""
    with engine.connect() as c:
        r = c.execute(text("""
            SELECT (SELECT count(*) FROM thiet_bi_iot) AS thiet_bi,
                   (SELECT count(*) FROM thiet_bi_iot WHERE toado IS NOT NULL) AS co_toado,
                   (SELECT count(*) FROM du_lieu_iot) AS so_do_tho,
                   (SELECT min(thoi_gian) FROM du_lieu_iot) AS tho_tu,
                   (SELECT count(*) FROM du_lieu_iot_gio) AS so_gio,
                   (SELECT min(gio) FROM du_lieu_iot_gio) AS gio_tu""")).fetchone()
    return {"thiet_bi": r.thiet_bi, "thiet_bi_co_toa_do_postgis": r.co_toado, "so_do_tho_7_ngay": r.so_do_tho,
            "so_do_tho_tu": r.tho_tu.isoformat() if r.tho_tu else None, "so_gio_da_tong_hop": r.so_gio,
            "tong_hop_tu": r.gio_tu.isoformat() if r.gio_tu else None,
            "chinh_sach": "Số đo thô giữ 7 ngày; tổng hợp theo giờ giữ lâu dài"}


@router.get("/api/v1/iot/canh-bao")
def canh_bao_gan_day(limit: int = 10):
    """Thư cảnh báo do trạm IoT tạo (ẩn email người nhận)."""
    limit = max(1, min(limit, 50))
    try:
        with engine.connect() as c:
            rows = c.execute(text("""SELECT thoi_gian, ma_tram, aqi, tieu_de, noi_dung, trang_thai FROM thu_da_gui
                                     WHERE loai = 'iot' ORDER BY id DESC LIMIT :l"""), {"l": limit}).fetchall()
    except Exception:
        return []
    return [{"thoi_gian": r.thoi_gian.strftime("%Y-%m-%d %H:%M:%S"), "ma": r.ma_tram, "aqi": r.aqi, "tieu_de": r.tieu_de,
             "noi_dung": r.noi_dung, "trang_thai": r.trang_thai} for r in rows]


@router.get("/api/v1/iot/bang-dien-tu")
def bang_dien_tu():
    """Đúng nội dung đang phát cho bảng điện tử qua MQTT (xem trên web để đối chiếu)."""
    return iot_service.du_lieu_bang()


@router.get("/api/v1/iot/nhat-ky")
def nhat_ky_iot(limit: int = 15):
    """Nhật ký của riêng module IoT (kết nối MQTT, vượt ngưỡng, trở lại dưới ngưỡng) – không chứa thông tin nhạy cảm."""
    limit = max(1, min(limit, 50))
    try:
        with engine.connect() as c:
            rows = c.execute(text("""SELECT thoi_gian, muc, su_kien, noi_dung FROM nhat_ky_he_thong
                                     WHERE nguon = 'iot' ORDER BY id DESC LIMIT :l"""), {"l": limit}).fetchall()
    except Exception:
        return []
    return [{"thoi_gian": r.thoi_gian.strftime("%Y-%m-%d %H:%M:%S"), "muc": r.muc, "su_kien": r.su_kien, "noi_dung": r.noi_dung}
            for r in rows]
