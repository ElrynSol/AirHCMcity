"""
Đồng bộ dữ liệu tự động (Open-Meteo + Sentinel-5P/GEE), TỰ LẤY BÙ các ngày còn thiếu.

Được gọi bởi (không cần mở terminal):
  - Windows Task Scheduler "AQI_DongBoHangNgay" (7:30 hằng ngày; máy tắt lúc đó thì chạy ngay khi bật lại)
  - Backend FastAPI (services/dong_bo.py): kiểm tra định kỳ khi máy chủ đang chạy + nút "Đồng bộ ngay" cho admin
  - Hoặc chạy tay:  venv\\Scripts\\python.exe data_pipeline\\dong_bo_hang_ngay.py [--kiem-tra]

Cách chọn khoảng ngày (tính theo dữ liệu đang có trong CSDL, nên lỡ lịch vài ngày vẫn tự bù):
  - Open-Meteo: từ min(ngày cuối trong CSDL + 1, hôm qua − 2) đến hôm qua. Luôn làm mới 3 ngày gần nhất vì
    số liệu thời tiết lưu trữ (archive) có độ trễ vài ngày; ngày chưa đủ số liệu sẽ được lấy lại ở lần sau.
  - GEE: từ max(ngày GEE cuối + 1, hôm nay − 30) đến hôm nay − 5. Sentinel-5P OFFL trễ khoảng 1 tuần;
    ngày chưa có ảnh không được lưu nên lần sau tự thử lại.
  Cả hai bước ghi bằng ON CONFLICT DO UPDATE nên chạy lặp lại không sinh dữ liệu trùng.

Ghi lại: bảng lich_su_dong_bo (web hiển thị ở trang Trạng thái dữ liệu), nhat_ky_he_thong (nguon = 'dong_bo'),
tệp log_dong_bo.txt ở thư mục gốc (tự xoay vòng khi > 1 MB). Khóa tệp tránh 2 lần chạy chồng nhau.
Mã thoát: 0 = thành công / không có gì cần lấy, 1 = một phần lỗi, 2 = lỗi, 3 = đang có lần chạy khác.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

THU_MUC = Path(__file__).resolve().parent
GOC = THU_MUC.parent
TEP_LOG = GOC / "log_dong_bo.txt"
TEP_KHOA = THU_MUC / ".dong_bo.lock"
KHOA_CU_GIAY = 2 * 3600              # khóa quá 2 giờ coi như sót lại từ lần chạy bị tắt ngang
GIOI_HAN_GIAY = {"openmeteo": 30 * 60, "gee": 40 * 60}

sys.path.insert(0, str(THU_MUC))
from stations_config import get_engine  # noqa: E402
from sqlalchemy import text  # noqa: E402


# ---------- Nhật ký ----------
def log(msg):
    dong = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    try:
        if TEP_LOG.exists() and TEP_LOG.stat().st_size > 1_000_000:
            TEP_LOG.replace(TEP_LOG.with_suffix(".txt.1"))
        with open(TEP_LOG, "a", encoding="utf-8") as f:
            f.write(dong + "\n")
    except OSError:
        pass
    if sys.stdout is not None:          # pythonw (chạy nền) không có console
        try:
            print(dong, flush=True)
        except Exception:
            pass


def ghi_nhat_ky_he_thong(conn, muc, su_kien, noi_dung, **chi_tiet):
    try:
        conn.execute(text("""INSERT INTO nhat_ky_he_thong (muc, nguon, su_kien, noi_dung, chi_tiet)
                             VALUES (:m, 'dong_bo', :s, :n, CAST(:c AS JSONB))"""),
                     {"m": muc, "s": su_kien, "n": noi_dung[:2000], "c": json.dumps(chi_tiet, ensure_ascii=False, default=str)})
    except Exception:
        pass   # bảng nhật ký do backend tạo; chưa có thì bỏ qua


# ---------- Khóa chống chạy chồng ----------
def lay_khoa():
    for _ in range(2):
        try:
            fd = os.open(TEP_KHOA, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()} {time.time():.0f}".encode())
            os.close(fd)
            return True
        except FileExistsError:
            try:
                if time.time() - TEP_KHOA.stat().st_mtime > KHOA_CU_GIAY:
                    TEP_KHOA.unlink()
                    continue
            except OSError:
                continue
            return False
    return False


def tra_khoa():
    try:
        TEP_KHOA.unlink()
    except OSError:
        pass


# ---------- Lịch sử ----------
def tao_bang(conn):
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS lich_su_dong_bo (
            id SERIAL PRIMARY KEY,
            bat_dau TIMESTAMP NOT NULL DEFAULT NOW(),
            ket_thuc TIMESTAMP,
            nguon_kich_hoat VARCHAR(30) NOT NULL,
            trang_thai VARCHAR(20) NOT NULL DEFAULT 'dang_chay',
            openmeteo_tu DATE, openmeteo_den DATE, so_dong_openmeteo INTEGER,
            gee_tu DATE, gee_den DATE, so_dong_gee INTEGER,
            ghi_chu TEXT
        )"""))


# Ngày cuối có dữ liệu của TRẠM CŨ NHẤT (trong các trạm đang hoạt động): 1 trạm lỗi mạng hôm nay sẽ được bù lần sau
# (nếu lấy MAX của cả bảng, các trạm khác đã có ngày mới sẽ che mất chỗ thiếu của trạm lỗi).
SQL_NGAY_CUOI_TRAM_CU_NHAT = """
        SELECT MIN(COALESCE(x.cuoi, DATE '1900-01-01')) FROM (
            SELECT t.id, MAX(d.ngay_do) AS cuoi FROM tram_quan_trac t
            LEFT JOIN {bang} d ON d.tram_id = t.id
            WHERE t.trang_thai = 'Hoat Dong' GROUP BY t.id) x"""

SQL_TRAM_THIEU_90_NGAY = """
        SELECT COUNT(*) FROM (
            SELECT t.id, COUNT(d.ngay_do) AS so_ngay
            FROM tram_quan_trac t
            LEFT JOIN du_lieu_tram_mat_dat d ON d.tram_id = t.id AND d.ngay_do >= CURRENT_DATE - 92
            WHERE t.trang_thai = 'Hoat Dong'
            GROUP BY t.id
            HAVING COUNT(d.ngay_do) < 88
        ) x"""


def ngay_cuoi_tram_cu_nhat(conn, bang):
    v = conn.execute(text(SQL_NGAY_CUOI_TRAM_CU_NHAT.format(bang=bang))).scalar()
    return None if v is None or v.year == 1900 else v


def khoang_ngay(conn, hom_nay):
    (om_tu, om_den), gee = tinh_khoang(hom_nay, ngay_cuoi_tram_cu_nhat(conn, "du_lieu_tram_mat_dat"),
                                       ngay_cuoi_tram_cu_nhat(conn, "du_lieu_gee_tphcm"))
    try:
        thieu_90 = conn.execute(text(SQL_TRAM_THIEU_90_NGAY)).scalar() or 0
        if thieu_90 > 0:
            om_tu = min(om_tu, hom_nay - timedelta(days=95))
    except Exception:
        pass
    return (om_tu, om_den), gee


def tinh_khoang(hom_nay, om_cuoi, gee_cuoi):
    """Khoảng ngày cần tải: ((om_tu, om_den), (gee_tu, gee_den) | None). Hàm thuần, có kiểm thử."""
    hom_qua = hom_nay - timedelta(days=1)
    om_tu = min((om_cuoi + timedelta(days=1)) if om_cuoi else hom_qua - timedelta(days=30), hom_qua - timedelta(days=2))
    om_tu = max(om_tu, hom_qua - timedelta(days=60))          # lỡ quá lâu: chỉ bù 60 ngày gần nhất
    gee_den = hom_nay - timedelta(days=5)
    gee_tu = max((gee_cuoi + timedelta(days=1)) if gee_cuoi else gee_den - timedelta(days=30), hom_nay - timedelta(days=30))
    return (om_tu, hom_qua), ((gee_tu, gee_den) if gee_tu <= gee_den else None)


def dem_dong(conn, bang, t0):
    return conn.execute(text(f"SELECT COUNT(*) FROM {bang} WHERE ngay_cap_nhat >= :t"), {"t": t0}).scalar() or 0


def chay_buoc(ten, script, tu, den):
    """Chạy script tải dữ liệu trong tiến trình con (không bật cửa sổ console), ghi đầu ra vào log."""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":            # tiến trình con cần python.exe để có stdout
        exe = exe.with_name("python.exe")
    co = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    log(f"{ten}: tải {tu} → {den}")
    try:
        kq = subprocess.run([str(exe), str(THU_MUC / script), "--start", str(tu), "--end", str(den)], cwd=str(THU_MUC),
                            capture_output=True, text=True, encoding="utf-8", errors="replace",
                            timeout=GIOI_HAN_GIAY[ten], creationflags=co, env=env)
    except subprocess.TimeoutExpired:
        log(f"{ten}: QUÁ THỜI GIAN {GIOI_HAN_GIAY[ten] // 60} phút")
        return False, "quá thời gian"
    dau_ra = (kq.stdout or "") + (kq.stderr or "")
    with open(TEP_LOG, "a", encoding="utf-8") as f:
        f.write(dau_ra.rstrip() + "\n")
    so_loi_tram = dau_ra.count("❌")
    if kq.returncode != 0:
        dong_cuoi = [d for d in dau_ra.strip().splitlines() if d.strip()][-1:] or ["(không có đầu ra)"]
        log(f"{ten}: LỖI mã {kq.returncode}: {dong_cuoi[0][:300]}")
        return False, dong_cuoi[0][:300]
    if so_loi_tram:
        log(f"{ten}: xong, {so_loi_tram} trạm lỗi (sẽ thử lại lần sau)")
        return None, f"{so_loi_tram} trạm lỗi"
    log(f"{ten}: xong")
    return True, ""


def main():
    ap = argparse.ArgumentParser(description="Đồng bộ dữ liệu tự động, tự lấy bù ngày thiếu")
    ap.add_argument("--nguon", default="tay", help="ai kích hoạt: lich_windows | may_chu | admin | tay")
    ap.add_argument("--kiem-tra", action="store_true", help="chỉ in khoảng ngày sẽ tải, không tải")
    ap.add_argument("--bo-gee", action="store_true", help="bỏ qua bước GEE")
    a = ap.parse_args()

    engine = get_engine()
    hom_nay = date.today()
    with engine.begin() as conn:
        tao_bang(conn)
        (om_tu, om_den), gee = khoang_ngay(conn, hom_nay)
    if a.kiem_tra:
        log(f"[kiểm tra] Open-Meteo {om_tu} → {om_den}; GEE {gee[0]} → {gee[1]}" if gee else
            f"[kiểm tra] Open-Meteo {om_tu} → {om_den}; GEE: chưa có ngày mới")
        return 0

    if not lay_khoa():
        log("Đang có một lần đồng bộ khác chạy, bỏ qua.")
        return 3
    t0 = datetime.now()
    try:
        with engine.begin() as conn:
            run_id = conn.execute(text("""INSERT INTO lich_su_dong_bo (nguon_kich_hoat, openmeteo_tu, openmeteo_den, gee_tu, gee_den)
                                          VALUES (:n, :ot, :od, :gt, :gd) RETURNING id"""),
                                  {"n": a.nguon[:30], "ot": om_tu, "od": om_den,
                                   "gt": gee[0] if gee else None, "gd": gee[1] if gee else None}).scalar()
        log(f"=== BẮT ĐẦU ĐỒNG BỘ #{run_id} (kích hoạt: {a.nguon}) ===")

        ket_qua, ghi_chu = [], []
        if gee and not a.bo_gee:
            ok, gc = chay_buoc("gee", "download_gee_data.py", *gee)
            ket_qua.append(ok); ghi_chu += [f"GEE: {gc}"] if gc else []
        ok, gc = chay_buoc("openmeteo", "download_openmeteo_data.py", om_tu, om_den)
        ket_qua.append(ok); ghi_chu += [f"Open-Meteo: {gc}"] if gc else []

        trang_thai = "thanh_cong" if all(k is True for k in ket_qua) else ("loi" if all(k is False for k in ket_qua) else "mot_phan")
        with engine.begin() as conn:
            n_om, n_gee = dem_dong(conn, "du_lieu_tram_mat_dat", t0), dem_dong(conn, "du_lieu_gee_tphcm", t0)
            conn.execute(text("""UPDATE lich_su_dong_bo SET ket_thuc = NOW(), trang_thai = :s, so_dong_openmeteo = :a,
                                 so_dong_gee = :b, ghi_chu = :g WHERE id = :id"""),
                         {"s": trang_thai, "a": n_om, "b": n_gee, "g": "; ".join(ghi_chu) or None, "id": run_id})
            ghi_nhat_ky_he_thong(conn, "INFO" if trang_thai == "thanh_cong" else "WARN", f"dong_bo_{trang_thai}",
                                 f"#{run_id} ({a.nguon}): Open-Meteo {om_tu}→{om_den} {n_om} dòng; GEE {n_gee} dòng"
                                 + (f" · {'; '.join(ghi_chu)}" if ghi_chu else ""), id=run_id)
        log(f"=== KẾT THÚC #{run_id}: {trang_thai} · Open-Meteo {n_om} dòng · GEE {n_gee} dòng ({(datetime.now() - t0).seconds}s) ===\n")
        return {"thanh_cong": 0, "mot_phan": 1, "loi": 2}[trang_thai]
    except Exception as exc:
        log(f"LỖI: {type(exc).__name__}: {exc}")
        try:
            with engine.begin() as conn:
                conn.execute(text("""UPDATE lich_su_dong_bo SET ket_thuc = NOW(), trang_thai = 'loi', ghi_chu = :g
                                     WHERE ket_thuc IS NULL AND bat_dau >= :t"""), {"g": f"{type(exc).__name__}: {exc}"[:500], "t": t0})
        except Exception:
            pass
        return 2
    finally:
        tra_khoa()


if __name__ == "__main__":
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    sys.exit(main())
