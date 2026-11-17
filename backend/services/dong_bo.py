"""Lịch đồng bộ dữ liệu chạy trong máy chủ FastAPI (bổ sung cho Windows Task Scheduler, không thay thế).

- Mỗi ngày 1 lần lúc DONG_BO_GIO (mặc định 07:45, sau lịch Windows 07:30): nếu hôm nay chưa có lần đồng bộ thành công thì chạy.
- Mỗi 10 phút: nếu dữ liệu Open-Meteo chưa có ngày hôm qua và 3 giờ gần đây chưa thử lần nào thì chạy
  (máy ngủ/tắt qua giờ hẹn vẫn tự bù khi máy chủ chạy lại).
- Admin bấm "Đồng bộ ngay" trên web → chay_ngay("admin").
Việc tải thật do data_pipeline/dong_bo_hang_ngay.py làm trong tiến trình con (không chặn API, không bật cửa sổ);
script đó có khóa tệp nên lịch Windows và lịch máy chủ trùng giờ cũng không chạy chồng.
Tắt: DONG_BO_BAT=0 trong .env.
"""

from core import config  # noqa: F401
import os
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import text

from core import logbus
from database import engine

GOC = Path(__file__).resolve().parents[2]
SCRIPT = GOC / "data_pipeline" / "dong_bo_hang_ngay.py"
TEP_KHOA = GOC / "data_pipeline" / ".dong_bo.lock"
TEP_LOG = GOC / "log_dong_bo.txt"
BAT = os.getenv("DONG_BO_BAT", "1") != "0"
GIO_CHAY = os.getenv("DONG_BO_GIO", "07:45")
CHU_KY_KIEM_TRA = 600          # giây
# Ngày cuối có dữ liệu của trạm đang hoạt động thiếu lâu nhất (trạm mới chưa có dữ liệu → NULL → coi như rất cũ)
SQL_TRAM_CU_NHAT = """
    SELECT MIN(COALESCE(x.cuoi, DATE '1900-01-01')) FROM (
        SELECT t.id, MAX(d.ngay_do) AS cuoi FROM tram_quan_trac t
        LEFT JOIN du_lieu_tram_mat_dat d ON d.tram_id = t.id
        WHERE t.trang_thai = 'Hoat Dong' GROUP BY t.id) x"""
CACH_LAN_THU = timedelta(hours=3)

_tien_trinh = None
_khoa = threading.Lock()
_luong = None


def _gio_phut():
    try:
        h, m = GIO_CHAY.split(":")
        return int(h), int(m)
    except ValueError:
        return 7, 45


def dang_chay() -> bool:
    if _tien_trinh is not None and _tien_trinh.poll() is None:
        return True
    try:   # lần chạy do lịch Windows hoặc chạy tay giữ khóa tệp
        return TEP_KHOA.exists() and time.time() - TEP_KHOA.stat().st_mtime < 2 * 3600
    except OSError:
        return False


def chay_ngay(nguon: str) -> bool:
    """Khởi động 1 lần đồng bộ trong tiến trình con. Trả False nếu đang có lần khác chạy."""
    global _tien_trinh
    with _khoa:
        if dang_chay():
            return False
        exe = Path(sys.executable)
        if exe.name.lower() == "pythonw.exe":
            exe = exe.with_name("python.exe")
        _tien_trinh = subprocess.Popen(
            [str(exe), str(SCRIPT), "--nguon", nguon], cwd=str(GOC),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    logbus.ghi("INFO", "dong_bo", "bat_dau", f"Khởi động đồng bộ (kích hoạt: {nguon}), PID {_tien_trinh.pid}")
    threading.Thread(target=_cho_xong, args=(_tien_trinh, nguon), name="cho-dong-bo", daemon=True).start()
    return True


def _cho_xong(p, nguon):
    """Chờ tiến trình đồng bộ kết thúc rồi phát sự kiện dong_bo.xong (đẩy tới trình duyệt qua SSE)."""
    ma = p.wait()
    try:
        from core import events
        with engine.connect() as c:
            r = c.execute(text("SELECT id, trang_thai, so_dong_openmeteo, so_dong_gee FROM lich_su_dong_bo ORDER BY id DESC LIMIT 1")).fetchone()
        events.publish("dong_bo.xong", {"nguon": nguon, "ma_thoat": ma, "id": r.id if r else None, "trang_thai": r.trang_thai if r else None,
                                        "so_dong_openmeteo": r.so_dong_openmeteo if r else None, "so_dong_gee": r.so_dong_gee if r else None})
    except Exception as exc:
        logbus.ghi("WARN", "dong_bo", "phat_su_kien_loi", f"{type(exc).__name__}: {exc}")


def _lan_gan_nhat(conn, chi_thanh_cong=False):
    try:
        return conn.execute(text("SELECT MAX(bat_dau) FROM lich_su_dong_bo"
                                 + (" WHERE trang_thai = 'thanh_cong'" if chi_thanh_cong else ""))).scalar()
    except Exception:
        return None   # bảng chưa tạo (chưa đồng bộ lần nào)


def can_dong_bo(bay_gio: datetime = None):
    """Trả lý do cần đồng bộ, hoặc None."""
    bay_gio = bay_gio or datetime.now()
    with engine.connect() as c:
        cuoi = c.execute(text(SQL_TRAM_CU_NHAT)).scalar()      # trạm thiếu dữ liệu lâu nhất quyết định
        lan_thu = _lan_gan_nhat(c)
        lan_ok = _lan_gan_nhat(c, chi_thanh_cong=True)
    return quyet_dinh(bay_gio, cuoi, lan_thu, lan_ok, _gio_phut())


def quyet_dinh(bay_gio, cuoi, lan_thu, lan_ok, gio_phut):
    """Hàm thuần (có kiểm thử): cuoi = ngày cuối của trạm thiếu lâu nhất; lan_thu / lan_ok = lần chạy gần nhất / thành công gần nhất."""
    h, m = gio_phut
    if bay_gio >= bay_gio.replace(hour=h, minute=m, second=0, microsecond=0) and (lan_ok is None or lan_ok.date() < bay_gio.date()) \
            and (lan_thu is None or bay_gio - lan_thu > CACH_LAN_THU):
        return f"lịch hằng ngày {GIO_CHAY}"
    if (cuoi is None or cuoi < bay_gio.date() - timedelta(days=1)) and (lan_thu is None or bay_gio - lan_thu > CACH_LAN_THU):
        return f"có trạm mới chỉ có dữ liệu tới {cuoi}, thiếu ngày hôm qua"
    return None


def _don_lan_bi_ngat():
    """Lần chạy bị ngắt giữa chừng (tắt máy, đóng cửa sổ) không kịp ghi kết thúc: quá 2 giờ mà không còn chạy thì đánh dấu lỗi."""
    if dang_chay():
        return
    with engine.begin() as c:
        n = c.execute(text("""UPDATE lich_su_dong_bo SET trang_thai = 'loi', ket_thuc = NOW(),
                                     ghi_chu = COALESCE(ghi_chu || '; ', '') || 'Bị ngắt giữa chừng (máy tắt/ngủ hoặc tiến trình bị dừng)'
                              WHERE trang_thai = 'dang_chay' AND bat_dau < NOW() - INTERVAL '2 hours'""")).rowcount
    if n:
        logbus.ghi("WARN", "dong_bo", "don_lan_bi_ngat", f"Đánh dấu {n} lần đồng bộ bị ngắt giữa chừng là lỗi")


def _vong_lap():
    time.sleep(90)   # chờ máy chủ khởi động xong
    while True:
        try:
            _don_lan_bi_ngat()
            ly_do = can_dong_bo()
            if ly_do and not dang_chay():
                logbus.ghi("INFO", "dong_bo", "tu_dong", f"Tự đồng bộ: {ly_do}")
                chay_ngay("may_chu")
        except Exception as exc:
            logbus.ghi("WARN", "dong_bo", "lich_loi", f"{type(exc).__name__}: {exc}")
        time.sleep(CHU_KY_KIEM_TRA)


def khoi_dong():
    global _luong
    if not BAT or _luong is not None:
        return
    _luong = threading.Thread(target=_vong_lap, name="lich-dong-bo", daemon=True)
    _luong.start()


def trang_thai() -> dict:
    with engine.connect() as c:
        om = c.execute(text("SELECT MAX(ngay_do), MAX(ngay_cap_nhat) FROM du_lieu_tram_mat_dat")).fetchone()
        om_cu_nhat = c.execute(text(SQL_TRAM_CU_NHAT)).scalar()
        gee = c.execute(text("SELECT MAX(ngay_do), MAX(ngay_cap_nhat) FROM du_lieu_gee_tphcm")).fetchone()
        try:
            ls = c.execute(text("""SELECT id, bat_dau, ket_thuc, nguon_kich_hoat, trang_thai, openmeteo_tu, openmeteo_den,
                                          so_dong_openmeteo, gee_tu, gee_den, so_dong_gee, ghi_chu
                                   FROM lich_su_dong_bo ORDER BY id DESC LIMIT 10""")).fetchall()
        except Exception:
            ls = []
    h, m = _gio_phut()
    bay_gio = datetime.now()
    lan_ke = bay_gio.replace(hour=h, minute=m, second=0, microsecond=0)
    if lan_ke <= bay_gio:
        lan_ke += timedelta(days=1)
    s = lambda v: v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else (str(v) if v is not None else None)
    hom_qua = date.today() - timedelta(days=1)
    return {
        "lich_may_chu_bat": BAT, "gio_chay": GIO_CHAY, "lan_hen_ke": s(lan_ke), "dang_chay": dang_chay(),
        "du_lieu": {"openmeteo_den": s(om[0]), "openmeteo_cap_nhat": s(om[1]), "openmeteo_du": bool(om_cu_nhat and om_cu_nhat >= hom_qua),
                    "openmeteo_tram_cu_nhat": s(om_cu_nhat),
                    "gee_den": s(gee[0]), "gee_cap_nhat": s(gee[1])},
        "lich_su": [{"id": r.id, "bat_dau": s(r.bat_dau), "ket_thuc": s(r.ket_thuc), "nguon": r.nguon_kich_hoat,
                     "trang_thai": r.trang_thai, "openmeteo": f"{r.openmeteo_tu} → {r.openmeteo_den}" if r.openmeteo_tu else None,
                     "so_dong_openmeteo": r.so_dong_openmeteo, "gee": f"{r.gee_tu} → {r.gee_den}" if r.gee_tu else None,
                     "so_dong_gee": r.so_dong_gee, "ghi_chu": r.ghi_chu} for r in ls],
    }


def doc_log(so_dong: int = 80) -> str:
    try:
        with open(TEP_LOG, encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-so_dong:])
    except OSError:
        return ""
