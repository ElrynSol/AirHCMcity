"""Trạm cảm biến IoT (mô phỏng Wokwi) qua MQTT.

Luồng:
  ESP32 (Wokwi) ──MQTT──► broker ──► _khi_nhan_tin() ──► bảng du_lieu_iot (cờ mo_phong)
                                         └─► tính AQI (TB 1 phút) ──► sự kiện iot.vuot_nguong ──► thư cảnh báo
  _vong_phat_bang() ──MQTT retained──► bảng điện tử ESP32: AQI toàn TP (CSDL) + AQI trạm IoT mới nhất

Chủ đề (topic), <DU_AN> = MQTT_DU_AN trong .env:
  airhcm/<DU_AN>/tram/<ma_thiet_bi>/do   ← trạm gửi {"khoa", "pm25", "pm10", "nhiet_do", "do_am", "vi_do", "kinh_do", "che_do"}
  airhcm/<DU_AN>/bang/aqi                → bảng điện tử (retained)

Dữ liệu IoT là MÔ PHỎNG: lưu bảng riêng, không trộn vào du_lieu_tram_mat_dat và không dùng huấn luyện mô hình.
Broker công cộng ai cũng đọc được; trường "khoa" chỉ chặn gói tin lạ, không phải bảo mật thật (dùng broker riêng + TLS khi triển khai).
"""

from core import config  # noqa: F401  (nạp .env + sys.path, gồm ml/)
import json
import os
import re
import threading
import time
from datetime import datetime

from sqlalchemy import text

from core import events, logbus
from database import engine
from tinh_aqi import tinh_aqi_tong_hop, muc_aqi

MQTT_HOST = os.getenv("MQTT_HOST", "broker.hivemq.com")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
DU_AN = os.getenv("MQTT_DU_AN", "dhtnmt-1250080037")
KHOA_THIET_BI = os.getenv("IOT_KHOA_THIET_BI", "airhcm-demo-2026")
NGUONG_AQI = int(os.getenv("IOT_NGUONG_AQI", "100"))          # vượt ngưỡng → cảnh báo
EMAIL_NHAN = os.getenv("IOT_EMAIL_NHAN", "")                    # để trống: thư chỉ lưu vào Hộp thư đã gửi
TOPIC_TRAM = f"airhcm/{DU_AN}/tram/+/do"
TOPIC_BANG = f"airhcm/{DU_AN}/bang/aqi"
GIOI_HAN = {"pm25": (0, 1000), "pm10": (0, 2000), "nhiet_do": (-20, 70), "do_am": (0, 100)}
MA_HOP_LE = re.compile(r"^[A-Za-z0-9_-]{1,30}$")   # mã thiết bị lấy từ topic: chỉ chữ, số, _ và -

trang_thai = {"ket_noi": False, "broker": f"{MQTT_HOST}:{MQTT_PORT}", "du_an": DU_AN, "so_tin_nhan": 0,
              "so_tin_bo": 0, "tin_cuoi": None, "lan_phat_bang": None, "loi": None}
_dang_vuot = {}          # ma_thiet_bi -> True khi đang ở trạng thái vượt ngưỡng (có trễ 10 AQI để không báo dồn dập)
_lan_bao_cuoi = {}       # ma_thiet_bi -> thời điểm gửi cảnh báo cuối
_client = None
_khoa = threading.Lock()


# ---------- CSDL ----------
def tao_bang():
    with engine.begin() as c:
        c.execute(text("""
            CREATE TABLE IF NOT EXISTS thiet_bi_iot (
                ma VARCHAR(30) PRIMARY KEY,
                ten TEXT NOT NULL,
                vi_do DOUBLE PRECISION,
                kinh_do DOUBLE PRECISION,
                mo_phong BOOLEAN NOT NULL DEFAULT TRUE,
                tao_luc TIMESTAMP NOT NULL DEFAULT NOW()
            )"""))
        c.execute(text("""
            CREATE TABLE IF NOT EXISTS du_lieu_iot (
                id BIGSERIAL PRIMARY KEY,
                ma_thiet_bi VARCHAR(30) NOT NULL REFERENCES thiet_bi_iot(ma) ON DELETE CASCADE,
                thoi_gian TIMESTAMP NOT NULL DEFAULT NOW(),
                pm25 REAL, pm10 REAL, nhiet_do REAL, do_am REAL,
                aqi INTEGER, chat VARCHAR(10), che_do VARCHAR(20),
                mo_phong BOOLEAN NOT NULL DEFAULT TRUE
            )"""))
        c.execute(text("CREATE INDEX IF NOT EXISTS idx_du_lieu_iot_tb_tg ON du_lieu_iot (ma_thiet_bi, thoi_gian DESC)"))
        # PostGIS: vị trí thiết bị dạng hình học (Point, WGS84) + chỉ mục GiST, tự cập nhật từ vi_do/kinh_do
        c.execute(text("ALTER TABLE thiet_bi_iot ADD COLUMN IF NOT EXISTS toado geometry(Point, 4326)"))
        c.execute(text("ALTER TABLE thiet_bi_iot ADD COLUMN IF NOT EXISTS ma_phuong VARCHAR(10)"))
        c.execute(text("CREATE INDEX IF NOT EXISTS ix_thiet_bi_iot_toado ON thiet_bi_iot USING GIST (toado)"))
        c.execute(text("UPDATE thiet_bi_iot SET toado = ST_SetSRID(ST_MakePoint(kinh_do, vi_do), 4326) "
                       "WHERE vi_do IS NOT NULL AND kinh_do IS NOT NULL AND toado IS NULL"))
        if c.execute(text("SELECT to_regclass('phuong_xa') IS NOT NULL")).scalar():   # gán bù phường/xã chứa thiết bị
            c.execute(text("UPDATE thiet_bi_iot t SET ma_phuong = (SELECT px.ma FROM phuong_xa px WHERE ST_Contains(px.geom, t.toado) LIMIT 1) "
                           "WHERE t.toado IS NOT NULL AND t.ma_phuong IS NULL"))
        # Tổng hợp theo giờ, GIỮ LÂU DÀI (số đo thô chỉ giữ 7 ngày): phục vụ thống kê, đối chiếu với số liệu mô hình
        c.execute(text("""
            CREATE TABLE IF NOT EXISTS du_lieu_iot_gio (
                ma_thiet_bi VARCHAR(30) NOT NULL REFERENCES thiet_bi_iot(ma) ON DELETE CASCADE,
                gio TIMESTAMP NOT NULL,
                so_mau INTEGER NOT NULL,
                pm25_tb REAL, pm25_max REAL, pm10_tb REAL, nhiet_do_tb REAL, do_am_tb REAL, aqi_max INTEGER,
                mo_phong BOOLEAN NOT NULL DEFAULT TRUE,
                PRIMARY KEY (ma_thiet_bi, gio))"""))
        tong_hop_gio(c, gio=24 * 8)   # gộp phần còn sót trước khi xóa số đo thô cũ
        c.execute(text("DELETE FROM du_lieu_iot WHERE thoi_gian < NOW() - INTERVAL '7 days'"))


def tong_hop_gio(c, gio: int = 3):
    """Gộp số đo thô của `gio` giờ gần nhất thành bản ghi theo giờ (chạy lặp lại an toàn: ON CONFLICT cập nhật)."""
    c.execute(text("""
        INSERT INTO du_lieu_iot_gio (ma_thiet_bi, gio, so_mau, pm25_tb, pm25_max, pm10_tb, nhiet_do_tb, do_am_tb, aqi_max, mo_phong)
        SELECT ma_thiet_bi, date_trunc('hour', thoi_gian), count(*), avg(pm25), max(pm25), avg(pm10), avg(nhiet_do), avg(do_am),
               max(aqi), bool_and(mo_phong)
        FROM du_lieu_iot WHERE thoi_gian >= date_trunc('hour', NOW() - make_interval(hours => :g))
        GROUP BY 1, 2
        ON CONFLICT (ma_thiet_bi, gio) DO UPDATE SET so_mau = EXCLUDED.so_mau, pm25_tb = EXCLUDED.pm25_tb, pm25_max = EXCLUDED.pm25_max,
            pm10_tb = EXCLUDED.pm10_tb, nhiet_do_tb = EXCLUDED.nhiet_do_tb, do_am_tb = EXCLUDED.do_am_tb, aqi_max = EXCLUDED.aqi_max
    """), {"g": gio})


def _so(x, ten):
    """Ép kiểu số và kiểm tra khoảng hợp lệ; ngoài khoảng → None (loại giá trị lỗi cảm biến)."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    lo, hi = GIOI_HAN[ten]
    return round(v, 2) if lo <= v <= hi and v == v else None


def aqi_trung_binh_1_phut(conn, ma):
    """AQI tức thời của trạm IoT: từ PM2.5/PM10 trung bình 1 phút gần nhất (làm mượt nhiễu cảm biến).
    Lưu ý: AQI giờ chuẩn QĐ 1459 dùng NowCast 12 giờ; ở đây dùng TB ngắn để trình diễn luồng thời gian thực."""
    r = conn.execute(text("""
        SELECT AVG(pm25) AS pm25, AVG(pm10) AS pm10, COUNT(*) AS n FROM du_lieu_iot
        WHERE ma_thiet_bi = :m AND thoi_gian > NOW() - INTERVAL '1 minute'"""), {"m": ma}).fetchone()
    aqi, chat = tinh_aqi_tong_hop(pm25=r.pm25, pm10=r.pm10)
    return aqi, chat, r


# ---------- Nhận tin từ trạm ----------
def _khi_nhan_tin(_client, _userdata, msg):
    trang_thai["so_tin_nhan"] += 1
    try:
        ma = msg.topic.split("/")[3]
        d = json.loads(msg.payload.decode("utf-8"))
        if not MA_HOP_LE.match(ma) or not isinstance(d, dict) or d.get("khoa") != KHOA_THIET_BI:
            trang_thai["so_tin_bo"] += 1
            return
        gt = {k: _so(d.get(k), k) for k in GIOI_HAN}
        if gt["pm25"] is None and gt["pm10"] is None:
            trang_thai["so_tin_bo"] += 1
            return
        aqi_goi, chat_goi = tinh_aqi_tong_hop(pm25=gt["pm25"], pm10=gt["pm10"])
        with engine.begin() as c:
            c.execute(text("""
                INSERT INTO thiet_bi_iot (ma, ten, vi_do, kinh_do) VALUES (:m, :t, :la, :lo)
                ON CONFLICT (ma) DO UPDATE SET ten = EXCLUDED.ten, vi_do = COALESCE(EXCLUDED.vi_do, thiet_bi_iot.vi_do),
                                               kinh_do = COALESCE(EXCLUDED.kinh_do, thiet_bi_iot.kinh_do)"""),
                      {"m": ma, "t": _ten_an_toan(d.get("ten"), ma),
                       "la": _toa_do(d.get("vi_do"), 8, 12), "lo": _toa_do(d.get("kinh_do"), 105, 108)})
            # Cập nhật hình học + phường/xã chứa thiết bị (PostGIS ST_Contains) khi vị trí thay đổi
            c.execute(text("""
                UPDATE thiet_bi_iot t SET toado = g.p,
                    ma_phuong = (SELECT px.ma FROM phuong_xa px WHERE ST_Contains(px.geom, g.p) LIMIT 1)
                FROM (SELECT ST_SetSRID(ST_MakePoint(kinh_do, vi_do), 4326) AS p FROM thiet_bi_iot WHERE ma = :m) g
                WHERE t.ma = :m AND t.vi_do IS NOT NULL AND (t.toado IS NULL OR NOT ST_Equals(t.toado, g.p) OR t.ma_phuong IS NULL)
            """), {"m": ma})
            c.execute(text("""
                INSERT INTO du_lieu_iot (ma_thiet_bi, pm25, pm10, nhiet_do, do_am, aqi, chat, che_do)
                VALUES (:m, :pm25, :pm10, :nhiet_do, :do_am, :aqi, :chat, :cd)"""),
                      {"m": ma, **gt, "aqi": aqi_goi, "chat": chat_goi, "cd": str(d.get("che_do", ""))[:20]})
            aqi, chat, tb = aqi_trung_binh_1_phut(c, ma)
            if trang_thai["so_tin_nhan"] % 20 == 1:   # gộp theo giờ định kỳ (rẻ: chỉ quét 2 giờ gần nhất)
                tong_hop_gio(c, gio=2)
        trang_thai["tin_cuoi"] = datetime.now().strftime("%H:%M:%S")
        events.publish("iot.da_nhan", {"ma": ma, "aqi": aqi, "chat": chat, "pm25": gt["pm25"], "pm10": gt["pm10"],
                                       "nhiet_do": gt["nhiet_do"], "do_am": gt["do_am"], "che_do": str(d.get("che_do", ""))[:20],
                                       "luc": datetime.now().strftime("%H:%M:%S")})
        _kiem_tra_nguong(ma, aqi, chat, tb, d)
    except Exception as exc:
        trang_thai["so_tin_bo"] += 1
        logbus.ghi("WARN", "iot", "tin_loi", f"{msg.topic}: {type(exc).__name__}: {exc}")


_KY_TU_BO = set("<>\"'`&") | {chr(i) for i in range(32)} | {chr(127)}   # ký tự HTML + ký tự điều khiển


def _ten_an_toan(ten, ma):
    """Tên thiết bị do gói tin gửi lên (broker công cộng): bỏ ký tự điều khiển và ký tự HTML, giới hạn 80 ký tự."""
    t = "".join(c for c in str(ten or "") if c not in _KY_TU_BO).strip()[:80]
    return t or f"Trạm IoT {ma}"


def _toa_do(x, lo, hi):
    try:
        v = float(x)
        return v if lo <= v <= hi else None
    except (TypeError, ValueError):
        return None


def _kiem_tra_nguong(ma, aqi, chat, tb, d):
    """Phát sự kiện khi AQI (TB 1 phút) vượt ngưỡng; chỉ báo lại sau khi đã xuống dưới ngưỡng − 10 (trễ) và tối thiểu 2 phút."""
    if aqi is None:
        return
    if aqi >= NGUONG_AQI and not _dang_vuot.get(ma) and time.time() - _lan_bao_cuoi.get(ma, 0) > 120:
        _dang_vuot[ma] = True
        _lan_bao_cuoi[ma] = time.time()
        events.publish("iot.vuot_nguong", {"ma": ma, "aqi": aqi, "chat": chat, "pm25": tb.pm25, "pm10": tb.pm10,
                                           "nguong": NGUONG_AQI, "luc": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    elif aqi < NGUONG_AQI - 10 and _dang_vuot.get(ma):
        _dang_vuot[ma] = False
        logbus.ghi("INFO", "iot", "tro_lai_duoi_nguong", f"{ma}: AQI {aqi} < {NGUONG_AQI}")


def khi_vuot_nguong(sk: dict):
    """Consumer của iot.vuot_nguong: ghi nhật ký + soạn thư cảnh báo (lưu Hộp thư đã gửi; gửi thật nếu đặt IOT_EMAIL_NHAN)."""
    from services.canh_bao_service import _luu_thu
    from core.mailer import gui_mail_chung
    m = muc_aqi(sk["aqi"])
    with engine.connect() as c:
        tb = c.execute(text("SELECT ten FROM thiet_bi_iot WHERE ma = :m"), {"m": sk["ma"]}).fetchone()
    ten = tb.ten if tb else sk["ma"]
    logbus.ghi("WARN", "iot", "vuot_nguong", f"{sk['ma']}: AQI {sk['aqi']} ({m['muc']}) ≥ ngưỡng {sk['nguong']}", **sk)
    tieu_de = f"[AQI {sk['aqi']}] Cảnh báo tức thời tại {ten}" + ("" if "mô phỏng" in ten else " (trạm IoT mô phỏng)")
    noi_dung = (f"Trạm IoT {sk['ma']} - {ten} ghi nhận AQI {sk['aqi']} ({m['muc']}) lúc {sk['luc']}, "
                f"chất ô nhiễm chính: {sk['chat']}.\nPM2.5 TB 1 phút: {_f(sk['pm25'])} µg/m³ · PM10: {_f(sk['pm10'])} µg/m³.\n"
                f"Ngưỡng cảnh báo: {sk['nguong']}.\n\n"
                f"Khuyến nghị (QĐ 1459/QĐ-TCMT)\n- Người bình thường: {m['nguoi_binh_thuong']}\n- Nhóm nhạy cảm: {m['nhom_nhay_cam']}\n\n"
                "Ghi chú: dữ liệu từ trạm cảm biến MÔ PHỎNG (Wokwi), dùng để trình diễn luồng cảnh báo thời gian thực.\n"
                "— AirHCM · Hệ thống Giám sát & Dự báo Chất lượng Không khí TP.HCM")
    trang_thai_thu = "chi_luu"
    if EMAIL_NHAN:
        try:
            trang_thai_thu = "da_gui" if gui_mail_chung(EMAIL_NHAN, tieu_de, noi_dung) else "that_bai"
        except Exception as exc:
            trang_thai_thu = "that_bai"
            logbus.ghi("ERROR", "iot", "gui_mail_loi", f"{type(exc).__name__}: {exc}")
    _luu_thu(EMAIL_NHAN or "(chỉ lưu – chưa đặt IOT_EMAIL_NHAN)", sk["ma"], sk["aqi"], tieu_de, noi_dung, trang_thai_thu, loai="iot")


def _f(x):
    return "--" if x is None else f"{x:.1f}"


# ---------- Phát AQI cho bảng điện tử ----------
def du_lieu_bang():
    with engine.connect() as c:
        tp = c.execute(text("""
            SELECT ngay_do, AVG(COALESCE(pm25_smoothed, pm25_mean)) AS pm25, AVG(COALESCE(pm10_smoothed, pm10_mean)) AS pm10,
                   AVG(COALESCE(o3_smoothed, o3_mean)) AS o3
            FROM du_lieu_tram_mat_dat WHERE ngay_do = (SELECT MAX(ngay_do) FROM du_lieu_tram_mat_dat) GROUP BY ngay_do""")).fetchone()
        iot = c.execute(text("""
            SELECT d.ma_thiet_bi, t.ten, d.thoi_gian FROM du_lieu_iot d JOIN thiet_bi_iot t ON t.ma = d.ma_thiet_bi
            ORDER BY d.thoi_gian DESC LIMIT 1""")).fetchone()
        aqi_iot = None
        if iot:
            aqi_iot, chat_iot, _ = aqi_trung_binh_1_phut(c, iot.ma_thiet_bi)
    kq = {"t": datetime.now().strftime("%H:%M"), "tp": None, "iot": None}
    if tp:
        aqi, chat = tinh_aqi_tong_hop(pm25=tp.pm25, pm10=tp.pm10, o3=tp.o3)
        m = muc_aqi(aqi)
        kq["tp"] = {"aqi": aqi, "muc": m["muc"] if m else None, "muc_i": THU_TU.get(m["muc"]) if m else None,
                    "chat": chat, "ngay": str(tp.ngay_do), "pm25": round(tp.pm25, 1) if tp.pm25 else None}
    if iot and aqi_iot is not None:
        m = muc_aqi(aqi_iot)
        kq["iot"] = {"ma": iot.ma_thiet_bi, "aqi": aqi_iot, "muc": m["muc"], "muc_i": THU_TU.get(m["muc"]),
                     "tuoi_giay": int((datetime.now() - iot.thoi_gian).total_seconds())}
    return kq


THU_TU = {"Tốt": 0, "Trung bình": 1, "Kém": 2, "Xấu": 3, "Rất xấu": 4, "Nguy hại": 5}


def _vong_phat_bang():
    while True:
        try:
            if _client is not None and trang_thai["ket_noi"]:
                _client.publish(TOPIC_BANG, json.dumps(du_lieu_bang(), ensure_ascii=False), qos=1, retain=True)
                trang_thai["lan_phat_bang"] = datetime.now().strftime("%H:%M:%S")
        except Exception as exc:
            logbus.ghi("WARN", "iot", "phat_bang_loi", f"{type(exc).__name__}: {exc}")
        time.sleep(30)


def phat_bang_ngay():
    """Phát lại ngay (sau khi trạm IoT vượt ngưỡng, để bảng điện tử phản ứng nhanh)."""
    if _client is not None and trang_thai["ket_noi"]:
        _client.publish(TOPIC_BANG, json.dumps(du_lieu_bang(), ensure_ascii=False), qos=1, retain=True)
        trang_thai["lan_phat_bang"] = datetime.now().strftime("%H:%M:%S")


# ---------- Khởi động ----------
def khoi_dong():
    """Gọi 1 lần khi FastAPI khởi động. Tắt bằng IOT_BAT=0 trong .env."""
    global _client
    if os.getenv("IOT_BAT", "1") == "0":
        return
    with _khoa:
        if _client is not None:
            return
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            trang_thai["loi"] = "Chưa cài paho-mqtt (pip install paho-mqtt)"
            logbus.ghi("WARN", "iot", "thieu_thu_vien", trang_thai["loi"])
            return
        tao_bang()
        events.subscribe("iot.vuot_nguong", khi_vuot_nguong)
        events.subscribe("iot.vuot_nguong", lambda sk: phat_bang_ngay())
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"airhcm-server-{DU_AN}-{os.getpid()}")

        def khi_ket_noi(cl, _u, _f, rc, _p):
            trang_thai["ket_noi"] = not rc.is_failure
            if not rc.is_failure:
                cl.subscribe(TOPIC_TRAM, qos=1)
                logbus.ghi("INFO", "iot", "mqtt_ket_noi", f"{MQTT_HOST}:{MQTT_PORT} · nghe {TOPIC_TRAM}")
            else:
                trang_thai["loi"] = str(rc)

        def khi_mat_ket_noi(_cl, _u, _f, rc, _p):
            trang_thai["ket_noi"] = False
            logbus.ghi("WARN", "iot", "mqtt_mat_ket_noi", str(rc))

        c.on_connect = khi_ket_noi
        c.on_disconnect = khi_mat_ket_noi
        c.on_message = _khi_nhan_tin
        c.reconnect_delay_set(2, 60)
        try:
            c.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
            c.loop_start()
        except Exception as exc:
            trang_thai["loi"] = f"{type(exc).__name__}: {exc}"
            logbus.ghi("WARN", "iot", "mqtt_loi", trang_thai["loi"])
            return
        _client = c
        threading.Thread(target=_vong_phat_bang, name="iot-phat-bang", daemon=True).start()
