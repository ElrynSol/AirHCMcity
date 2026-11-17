"""Dịch vụ cảnh báo email: tạo bảng đăng ký, quét ngưỡng AQI và gửi thư."""

from core import config  # noqa: F401  (nạp .env và đường dẫn dự án trước)
from database import engine
from sqlalchemy import text
import os
from core.mailer import gui_mail_chung
from services.aqi import _aqi_helpers
from core import events, logbus
import threading


def _tao_bang_canh_bao():
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS dang_ky_canh_bao (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                tram_id INTEGER NOT NULL,
                nguong_aqi INTEGER NOT NULL DEFAULT 100,
                hoat_dong BOOLEAN NOT NULL DEFAULT TRUE,
                lan_gui_cuoi DATE,
                tao_luc TIMESTAMP DEFAULT NOW(),
                UNIQUE (email, tram_id)
            )
        """))


def _tao_bang_thu_da_gui():
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS thu_da_gui (
                id SERIAL PRIMARY KEY,
                thoi_gian TIMESTAMP NOT NULL DEFAULT NOW(),
                email VARCHAR(255) NOT NULL,
                ma_tram VARCHAR(50),
                aqi INTEGER,
                tieu_de TEXT,
                noi_dung TEXT,
                trang_thai VARCHAR(20) NOT NULL,
                loai VARCHAR(20) NOT NULL DEFAULT 'canh_bao'
            )
        """))


def _luu_thu(email, ma_tram, aqi, tieu_de, noi_dung, trang_thai, loai="canh_bao"):
    """Hộp thư đã gửi: trang_thai = da_gui | that_bai | chi_luu; loai = canh_bao | demo."""
    try:
        with engine.begin() as conn:
            conn.execute(text("""INSERT INTO thu_da_gui (email, ma_tram, aqi, tieu_de, noi_dung, trang_thai, loai)
                               VALUES (:e, :m, :a, :t, :n, :s, :l)"""),
                         {"e": email, "m": ma_tram, "a": aqi, "t": tieu_de, "n": noi_dung, "s": trang_thai, "l": loai})
    except Exception as exc:
        logbus.ghi("WARN", "mail", "luu_thu_that_bai", f"{type(exc).__name__}: {exc}")


def tao_noi_dung_thu(sk: dict):
    tieu_de = f"[AQI {sk['aqi']}] Cảnh báo không khí tại {sk['ten_tram']}"
    noi_dung = (
        f"Cảnh báo chất lượng không khí tại {sk['ma_tram']} - {sk['ten_tram']}\n\n"
        f"AQI ngày {sk['ngay']}: {sk['aqi']} ({sk['muc']}), chất ô nhiễm chính: {sk['chat']}.\n"
        f"Bạn đặt ngưỡng cảnh báo: {sk['nguong']}.\n\n"
        "Khuyến nghị: người nhạy cảm nên hạn chế hoạt động ngoài trời, đeo khẩu trang khi ra đường.\n\n"
        "Lưu ý: số liệu là ước tính từ mô hình, chưa kiểm chứng đo đạc mặt đất, chỉ mang tính tham khảo.\n"
        "Để hủy nhận cảnh báo, vào trang Cảnh báo trên hệ thống.\n"
        "— Hệ thống Giám sát & Dự báo Chất lượng Không khí TP.HCM"
    )
    return tieu_de, noi_dung


def danh_gia_canh_bao(tram_ids=None, dong_bo: bool = False) -> dict:
    """Bước 'tính AQI -> so ngưỡng'. Với mỗi đăng ký có AQI mới nhất >= ngưỡng thì phát sự kiện
    `aqi.vuot_nguong` (consumer sẽ gửi email). dong_bo=True: xử lý ngay (dùng cho nút admin) và trả kết quả.
    tram_ids=None: quét mọi trạm; ngược lại chỉ quét các trạm vừa có dữ liệu mới."""
    tinh_aqi_tong_hop, phan_loai_aqi = _aqi_helpers()
    ket_qua = {"da_gui": 0, "khong_dat_nguong_hoac_chua_co_du_lieu": 0, "loi": []}
    dieu_kien, tham_so = "", {}
    if tram_ids:
        dieu_kien = " AND d.tram_id = ANY(:ids)"
        tham_so["ids"] = [int(x) for x in tram_ids]
    with engine.begin() as conn:
        subs = conn.execute(text(f"""
            SELECT d.id, d.email, d.tram_id, d.nguong_aqi, t.ma_tram, t.ten_tram
            FROM dang_ky_canh_bao d JOIN tram_quan_trac t ON t.id = d.tram_id
            WHERE d.hoat_dong AND (d.lan_gui_cuoi IS NULL OR d.lan_gui_cuoi < CURRENT_DATE){dieu_kien}
        """), tham_so).fetchall()
        cache_tram = {}
        for s in subs:
            if s.tram_id not in cache_tram:
                cache_tram[s.tram_id] = conn.execute(text("""
                    SELECT ngay_do, COALESCE(pm25_smoothed, pm25_mean) AS pm25, COALESCE(pm10_smoothed, pm10_mean) AS pm10,
                           COALESCE(o3_smoothed, o3_mean) AS o3
                    FROM du_lieu_tram_mat_dat WHERE tram_id = :t ORDER BY ngay_do DESC LIMIT 1
                """), {"t": s.tram_id}).fetchone()
            m = cache_tram[s.tram_id]
            aqi, chat = (None, None)
            if m:
                aqi, chat = tinh_aqi_tong_hop(pm25=m.pm25, pm10=m.pm10, o3=m.o3)
            if aqi is None or aqi < s.nguong_aqi:
                ket_qua["khong_dat_nguong_hoac_chua_co_du_lieu"] += 1
                continue
            sk = {"dk_id": s.id, "email": s.email, "tram_id": s.tram_id, "ma_tram": s.ma_tram, "ten_tram": s.ten_tram,
                  "nguong": s.nguong_aqi, "aqi": aqi, "chat": chat, "muc": phan_loai_aqi(aqi), "ngay": str(m.ngay_do)}
            if dong_bo:
                kq = gui_mail_vuot_nguong(sk)
                if kq == "ok":
                    ket_qua["da_gui"] += 1
                elif kq not in ("da_gui_hom_nay",):
                    ket_qua["loi"].append(kq)
                    if kq.startswith("Chưa cấu hình SMTP"):
                        break
            else:
                events.publish("aqi.vuot_nguong", sk)
    return ket_qua


def gui_mail_vuot_nguong(sk: dict) -> str:
    """Consumer của sự kiện `aqi.vuot_nguong`: gửi email. Trả 'ok', 'da_gui_hom_nay' hoặc thông báo lỗi."""
    if not (os.getenv("SMTP_USER") and os.getenv("SMTP_PASS")):
        logbus.ghi("WARN", "mail", "aqi.vuot_nguong", f"Bỏ qua gửi tới {sk['email']}: chưa cấu hình SMTP", tram=sk["ma_tram"], aqi=sk["aqi"])
        return "Chưa cấu hình SMTP trong .env"
    # 'Giành' quyền gửi trước (nguyên tử) để tránh gửi trùng khi có 2 sự kiện cùng lúc
    with engine.begin() as conn:
        gianh = conn.execute(text("""
            UPDATE dang_ky_canh_bao SET lan_gui_cuoi = CURRENT_DATE
            WHERE id = :id AND hoat_dong AND (lan_gui_cuoi IS NULL OR lan_gui_cuoi < CURRENT_DATE) RETURNING id
        """), {"id": sk["dk_id"]}).fetchone()
    if not gianh:
        return "da_gui_hom_nay"
    tieu_de, noi_dung = tao_noi_dung_thu(sk)
    try:
        if gui_mail_chung(sk["email"], tieu_de, noi_dung):
            _luu_thu(sk["email"], sk["ma_tram"], sk["aqi"], tieu_de, noi_dung, "da_gui")
            logbus.ghi("INFO", "mail", "da_gui_canh_bao", f"Đã gửi cảnh báo AQI {sk['aqi']} tại {sk['ma_tram']}", nguoi_dung=sk["email"], tram=sk["ma_tram"], aqi=sk["aqi"])
            return "ok"
        raise RuntimeError("Chưa cấu hình SMTP trong .env")
    except Exception as exc:
        with engine.begin() as conn:  # trả lại quyền gửi để lần quét sau thử lại
            conn.execute(text("UPDATE dang_ky_canh_bao SET lan_gui_cuoi = NULL WHERE id = :id"), {"id": sk["dk_id"]})
        _luu_thu(sk["email"], sk["ma_tram"], sk["aqi"], tieu_de, noi_dung, "that_bai")
        logbus.ghi("ERROR", "mail", "gui_that_bai", f"{type(exc).__name__}: {exc}", nguoi_dung=sk["email"], tram=sk["ma_tram"])
        return f"{sk['email']}: {type(exc).__name__}: {exc}"


def chay_gui_canh_bao() -> dict:
    """Nút admin 'gửi cảnh báo ngay': quét toàn bộ đăng ký và gửi đồng bộ (giữ định dạng kết quả cũ)."""
    kq = danh_gia_canh_bao(None, dong_bo=True)
    logbus.ghi("INFO", "canh_bao", "quet_thu_cong", f"Đã gửi {kq['da_gui']}, lỗi {len(kq['loi'])}")
    return kq


# ----- Nạp dữ liệu mới -> (gom nhóm 20 giây) -> tính AQI -> sự kiện vượt ngưỡng ------------------------
_cho_tram = set()
_khoa = threading.Lock()
_timer = None


def _xu_ly_gom():
    global _timer
    with _khoa:
        ids = list(_cho_tram)
        _cho_tram.clear()
        _timer = None
    if ids:
        danh_gia_canh_bao(ids)
        logbus.ghi("INFO", "canh_bao", "danh_gia_sau_nap", f"Đánh giá lại {len(ids)} trạm sau khi có dữ liệu mới", tram_ids=ids)


def khi_du_lieu_da_nap(sk: dict):
    """Consumer của `du_lieu.da_nap`. Gom nhiều lần nạp liên tiếp thành 1 lần đánh giá để không gửi dồn dập."""
    global _timer
    logbus.ghi("INFO", "du_lieu", "da_nap", f"Có {sk.get('so_dong', '?')} dòng dữ liệu mới ({sk.get('op')}), trạm: {sk.get('tram_ids')}")
    with _khoa:
        _cho_tram.update(sk.get("tram_ids") or [])
        if _timer is None and _cho_tram:
            _timer = threading.Timer(20, _xu_ly_gom)
            _timer.daemon = True
            _timer.start()


def khi_tram_thay_doi(sk: dict):
    """Consumer của tram.da_tao/da_sua/da_xoa: ghi nhật ký; trạm mới thì làm nóng bộ nhớ đệm số liệu theo giờ."""
    nhan = {"INSERT": "thêm", "UPDATE": "sửa", "DELETE": "xóa"}.get(sk.get("op"), sk.get("op"))
    logbus.ghi("INFO", "cdc", f"tram.{nhan}", f"Phát hiện {nhan} trạm {sk.get('ma_tram')} (id {sk.get('tram_id')}) trong CSDL", tram_id=sk.get("tram_id"))
    if sk.get("op") == "INSERT":
        try:
            from services.openmeteo import lay_gio_hien_tai
            with engine.begin() as conn:
                r = conn.execute(text("SELECT ST_Y(toado::geometry) AS lat, ST_X(toado::geometry) AS lon FROM tram_quan_trac WHERE id = :i"),
                                 {"i": sk["tram_id"]}).fetchone()
            if r and r.lat is not None:
                kq = lay_gio_hien_tai([(r.lat, r.lon)])
                logbus.ghi("INFO" if kq else "WARN", "du_lieu", "lay_du_lieu_tram_moi",
                           "Đã lấy số liệu Open-Meteo ban đầu cho trạm mới" if kq else "Chưa lấy được số liệu Open-Meteo cho trạm mới (sẽ thử lại khi mở bản đồ)",
                           tram_id=sk["tram_id"])
        except Exception as exc:
            logbus.ghi("WARN", "du_lieu", "lay_du_lieu_tram_moi", f"{type(exc).__name__}: {exc}", tram_id=sk.get("tram_id"))


def dang_ky_consumer():
    events.subscribe("aqi.vuot_nguong", gui_mail_vuot_nguong)
    events.subscribe("du_lieu.da_nap", khi_du_lieu_da_nap)
    for ct in ("tram.da_tao", "tram.da_sua", "tram.da_xoa"):
        events.subscribe(ct, khi_tram_thay_doi)


def _vong_lap_canh_bao():
    """Lưới an toàn: mỗi 6 giờ quét lại toàn bộ (phòng khi bỏ lỡ thông báo CDC)."""
    import time
    time.sleep(60)
    while True:
        try:
            if os.getenv("SMTP_USER") and os.getenv("SMTP_PASS"):
                danh_gia_canh_bao(None)
        except Exception as exc:
            logbus.ghi("ERROR", "canh_bao", "vong_lap", f"{type(exc).__name__}: {exc}")
        time.sleep(6 * 3600)


def chay_demo(tram_id: int, nguong_thu: int, gui_that: bool, email_nhan: str) -> dict:
    """Chạy luồng cảnh báo TỪNG GIAI ĐOẠN để trình diễn. Dùng dữ liệu thật mới nhất của trạm.
    Không đụng giới hạn 1 thư/ngày và không cần đăng ký; thư đi tới chính email admin."""
    import time
    tinh_aqi_tong_hop, phan_loai_aqi = _aqi_helpers()
    cac_buoc = []

    def them(ten, trang_thai, chi_tiet, t0):
        cac_buoc.append({"ten": ten, "trang_thai": trang_thai, "chi_tiet": chi_tiet, "ms": int((time.time() - t0) * 1000)})
        logbus.ghi("INFO" if trang_thai != "loi" else "ERROR", "canh_bao", "demo_buoc", f"{ten}: {chi_tiet}", nguoi_dung=email_nhan)

    t0 = time.time()
    with engine.begin() as conn:
        tram = conn.execute(text("SELECT id, ma_tram, ten_tram FROM tram_quan_trac WHERE id = :i"), {"i": tram_id}).fetchone()
        if not tram:
            them("1. Chọn trạm", "loi", "Không tìm thấy trạm", t0)
            return {"cac_buoc": cac_buoc}
        m = conn.execute(text("""
            SELECT ngay_do, COALESCE(pm25_smoothed, pm25_mean) AS pm25, COALESCE(pm10_smoothed, pm10_mean) AS pm10,
                   COALESCE(o3_smoothed, o3_mean) AS o3
            FROM du_lieu_tram_mat_dat WHERE tram_id = :t ORDER BY ngay_do DESC LIMIT 1
        """), {"t": tram_id}).fetchone()
    if not m:
        them("1. Đọc dữ liệu mới nhất", "loi", f"Trạm {tram.ma_tram} chưa có dữ liệu trong du_lieu_tram_mat_dat", t0)
        return {"cac_buoc": cac_buoc}
    f = lambda v: "—" if v is None else round(v, 1)
    them("1. Đọc dữ liệu mới nhất của trạm", "ok",
         f"{tram.ma_tram} - {tram.ten_tram}, ngày {m.ngay_do}: PM2.5 {f(m.pm25)}, PM10 {f(m.pm10)}, O₃ {f(m.o3)} (µg/m³, ước tính mô hình)", t0)

    t0 = time.time()
    them("2. Phát sự kiện du_lieu.da_nap", "ok",
         "Thực tế do trigger CDC phát khi có dữ liệu nạp vào; ở chế độ trình diễn bước này được mô phỏng, còn dữ liệu đọc ở bước 1 là dữ liệu thật", t0)

    t0 = time.time()
    aqi, chat = tinh_aqi_tong_hop(pm25=m.pm25, pm10=m.pm10, o3=m.o3)
    if aqi is None:
        them("3. Tính AQI (QĐ 1459/QĐ-TCMT)", "loi", "Không đủ dữ liệu để tính AQI", t0)
        return {"cac_buoc": cac_buoc}
    muc = phan_loai_aqi(aqi)
    them("3. Tính AQI (QĐ 1459/QĐ-TCMT)", "ok", f"AQI = {aqi} ({muc}), chất ô nhiễm chính: {chat}", t0)

    t0 = time.time()
    if aqi < nguong_thu:
        them("4. So với ngưỡng", "bo_qua",
             f"AQI {aqi} < ngưỡng thử {nguong_thu}: không vượt ngưỡng nên hệ thống KHÔNG gửi cảnh báo. Hạ ngưỡng thử xuống thấp hơn để xem các bước tiếp theo.", t0)
        return {"cac_buoc": cac_buoc, "aqi": aqi}
    them("4. So với ngưỡng", "ok", f"AQI {aqi} ≥ ngưỡng thử {nguong_thu}: vượt ngưỡng", t0)

    t0 = time.time()
    sk = {"dk_id": None, "email": email_nhan, "tram_id": tram.id, "ma_tram": tram.ma_tram, "ten_tram": tram.ten_tram,
          "nguong": nguong_thu, "aqi": aqi, "chat": chat, "muc": muc, "ngay": str(m.ngay_do)}
    them("5. Phát sự kiện aqi.vuot_nguong", "ok", f"Sự kiện chuyển tới consumer gửi thư (người nhận: {email_nhan})", t0)

    t0 = time.time()
    tieu_de, noi_dung = tao_noi_dung_thu(sk)
    tieu_de = "[THỬ NGHIỆM] " + tieu_de
    them("6. Soạn nội dung thư", "ok", f"Tiêu đề: {tieu_de}", t0)

    t0 = time.time()
    co_smtp = bool(os.getenv("SMTP_USER") and os.getenv("SMTP_PASS"))
    if gui_that and co_smtp:
        try:
            gui_mail_chung(email_nhan, tieu_de, noi_dung)
            _luu_thu(email_nhan, tram.ma_tram, aqi, tieu_de, noi_dung, "da_gui", "demo")
            them("7. Gửi email (SMTP)", "ok", f"Đã gửi thật tới {email_nhan}", t0)
        except Exception as exc:
            _luu_thu(email_nhan, tram.ma_tram, aqi, tieu_de, noi_dung, "that_bai", "demo")
            them("7. Gửi email (SMTP)", "loi", f"{type(exc).__name__}: {exc}", t0)
    else:
        ly_do = "bạn không chọn gửi thật" if not gui_that else "chưa cấu hình SMTP trong .env"
        _luu_thu(email_nhan, tram.ma_tram, aqi, tieu_de, noi_dung, "chi_luu", "demo")
        them("7. Lưu vào Hộp thư đã gửi", "ok", f"Không gửi email thật ({ly_do}); nội dung thư được lưu để xem ngay bên dưới", t0)
    return {"cac_buoc": cac_buoc, "aqi": aqi}
