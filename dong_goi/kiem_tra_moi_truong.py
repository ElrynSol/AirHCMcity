"""Kiểm tra máy có đủ điều kiện chạy AirHCM không (Windows / Linux / macOS, x86-64 / ARM64).

    python dong_goi/kiem_tra_moi_truong.py            # chỉ kiểm tra, in báo cáo
    python dong_goi/kiem_tra_moi_truong.py --tao-csdl # tạo CSDL + bật PostGIS nếu chưa có

Kiểm tra: phiên bản Python, thư viện (đúng phiên bản trong requirements.txt), tài nguyên hệ điều hành (RAM, ổ đĩa, CPU,
cổng 8000), tệp cấu hình .env, kết nối PostgreSQL + PostGIS, tệp mô hình nạp được với thư viện hiện tại, thư mục web.
Mã thoát: 0 = đủ điều kiện chạy, 1 = còn lỗi phải sửa (cảnh báo không tính là lỗi).
"""

import argparse
import os
import platform
import re
import shutil
import socket
import sys
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent
LOI, CANH_BAO = [], []
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # cửa sổ lệnh Windows cũ (cp1252/cp1258) vẫn in được tiếng Việt
    except Exception:
        pass


def ok(m):
    print(f"  [OK]   {m}")


def canh_bao(m):
    CANH_BAO.append(m)
    print(f"  [!]    {m}")


def loi(m):
    LOI.append(m)
    print(f"  [LỖI]  {m}")


def ram_mb():
    try:
        if sys.platform == "win32":
            import ctypes

            class M(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("p", ctypes.c_ulong), ("t", ctypes.c_ulonglong), ("a", ctypes.c_ulonglong),
                            ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong), ("tv", ctypes.c_ulonglong),
                            ("av", ctypes.c_ulonglong), ("ae", ctypes.c_ulonglong)]
            m = M(); m.l = ctypes.sizeof(M)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.t // 2**20, m.a // 2**20
        if sys.platform == "darwin":
            import subprocess
            t = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"])) // 2**20
            return t, None
        d = dict(l.split(":", 1) for l in Path("/proc/meminfo").read_text().splitlines() if ":" in l)
        return int(d["MemTotal"].split()[0]) // 1024, int(d.get("MemAvailable", "0 kB").split()[0]) // 1024
    except Exception:
        return None, None


def kiem_he_thong():
    print("\n1. Hệ điều hành và tài nguyên")
    ok(f"{platform.system()} {platform.release()} · {platform.machine()} · {os.cpu_count()} CPU")
    v = sys.version_info
    if v < (3, 11):
        loi(f"Python {v.major}.{v.minor}: cần Python 3.11 trở lên (khuyến nghị 3.12)")
    else:
        ok(f"Python {v.major}.{v.minor}.{v.micro} ({sys.executable})")
    tong, con = ram_mb()
    if tong:
        (loi if tong < 1500 else canh_bao if tong < 3000 else ok)(
            f"RAM {tong:,} MB" + (f" (còn trống {con:,} MB)" if con else "") +
            ("" if tong >= 3000 else " — tối thiểu ~1,5 GB, khuyến nghị ≥ 3 GB (mô hình + pandas)"))
    trong = shutil.disk_usage(GOC).free // 2**30
    (loi if trong < 2 else canh_bao if trong < 5 else ok)(f"Ổ đĩa còn trống {trong} GB" + ("" if trong >= 5 else " — nên ≥ 5 GB"))
    if os.cpu_count() and os.cpu_count() < 2:
        canh_bao("Chỉ 1 CPU: huấn luyện mô hình sẽ chậm (máy chủ vẫn chạy được)")
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", int(os.getenv("CONG", "8000"))))
        ok(f"Cổng {os.getenv('CONG', '8000')} đang trống")
    except OSError:
        canh_bao(f"Cổng {os.getenv('CONG', '8000')} đang bị chiếm (máy chủ AirHCM đã chạy, hoặc phần mềm khác) — chỉ chạy 1 máy chủ")
    finally:
        s.close()
    if "OneDrive" in str(GOC) or "Dropbox" in str(GOC):
        canh_bao("Dự án nằm trong thư mục đồng bộ đám mây: .env, khóa bí mật bị tải lên mây, venv làm đồng bộ chậm — nên chuyển ra ngoài")


def kiem_thu_vien():
    print("\n2. Thư viện Python (so với requirements.txt)")
    from importlib import metadata
    ds = []
    for dong in (GOC / "requirements.txt").read_text(encoding="utf-8").splitlines():
        dong = dong.split("#")[0].strip()
        m = re.match(r"^([A-Za-z0-9_.\-]+)(\[[^\]]*\])?\s*(==|>=)\s*([^\s;]+)", dong)
        if m:
            ds.append((m.group(1), m.group(3), m.group(4)))
    thieu, sai = [], []
    for ten, ss, ban in ds:
        try:
            co = metadata.version(ten)
        except metadata.PackageNotFoundError:
            thieu.append(ten); continue
        if ss == "==" and co != ban:
            sai.append(f"{ten} {co} (cần {ban})")
    if thieu:
        loi(f"Thiếu {len(thieu)} thư viện: {', '.join(thieu[:8])}{'…' if len(thieu) > 8 else ''} → pip install -r requirements.txt")
    if sai:
        canh_bao("Khác phiên bản: " + "; ".join(sai[:6]) + " → pip install -r requirements.txt")
    if not thieu and not sai:
        ok(f"Đủ {len(ds)} thư viện, đúng phiên bản")


def doc_env():
    print("\n3. Tệp cấu hình .env")
    f = GOC / ".env"
    if not f.exists():
        loi("Chưa có .env → chạy cai_dat.ps1 (Windows) / cai_dat.sh (Linux, macOS), hoặc sao chép .env.example thành .env")
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(f)
    except ImportError:
        return
    if len(os.getenv("JWT_SECRET_KEY", "")) < 32:
        loi("JWT_SECRET_KEY thiếu hoặc ngắn hơn 32 ký tự")
    else:
        ok("JWT_SECRET_KEY hợp lệ")
    if os.getenv("MOI_TRUONG") == "production":
        if not os.getenv("ADMIN_EMAILS"):
            loi("MOI_TRUONG=production nhưng chưa đặt ADMIN_EMAILS (ai đăng ký đầu tiên sẽ thành admin)")
        if os.getenv("OTP_DEMO") == "1":
            loi("OTP_DEMO=1 trên máy chủ công khai: ai cũng đặt lại được mật khẩu người khác — đặt OTP_DEMO=0")
    if not (os.getenv("SMTP_USER") and os.getenv("SMTP_PASS")):
        canh_bao("Chưa cấu hình SMTP: quên mật khẩu và email cảnh báo không gửi được")
    else:
        ok("Đã cấu hình SMTP")


def kiem_csdl(tao: bool):
    print("\n4. PostgreSQL + PostGIS")
    sys.path.insert(0, str(GOC / "data_pipeline"))
    try:
        from db_url import db_url
        from sqlalchemy import create_engine, text
        from sqlalchemy.engine import make_url
    except ImportError as e:
        loi(f"Chưa cài thư viện CSDL ({e})"); return
    url = make_url(db_url())
    try:
        with create_engine(url, connect_args={"connect_timeout": 5}).connect() as c:
            ok(f"Kết nối {url.host}:{url.port}/{url.database} · {c.execute(text('SHOW server_version')).scalar()}")
            pg = c.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'postgis'")).scalar()
            if pg:
                ok(f"PostGIS {pg}")
            elif tao:
                c.execute(text("CREATE EXTENSION IF NOT EXISTS postgis")); c.commit(); ok("Đã bật PostGIS")
            else:
                loi("CSDL chưa bật PostGIS → chạy lại với --tao-csdl (cần cài gói PostGIS cho PostgreSQL)")
            so = c.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")).scalar()
            (ok if so > 3 else canh_bao)(f"{so} bảng" + ("" if so > 3 else " — CSDL trống: khôi phục backup.sql hoặc chạy data_pipeline/run_pipeline.py"))
    except Exception as e:
        thong_diep = str(e).splitlines()[0]
        if tao and "does not exist" in thong_diep:
            try:
                with create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT").connect() as c:
                    c.execute(text(f'CREATE DATABASE "{url.database}"'))
                ok(f"Đã tạo CSDL {url.database}"); return kiem_csdl(tao)
            except Exception as e2:
                loi(f"Không tạo được CSDL: {str(e2).splitlines()[0]}"); return
        loi(f"Không kết nối được CSDL ({thong_diep[:160]}) → kiểm tra PostgreSQL đã chạy, DB_* trong .env")


def kiem_mo_hinh():
    print("\n5. Mô hình đã huấn luyện và giao diện web")
    mh = GOC / "models"
    tep = sorted(list(mh.glob("*.pkl")) + list(mh.glob("*.joblib"))) if mh.exists() else []
    if not tep:
        canh_bao("Chưa có mô hình trong models/ → dự báo không chạy; huấn luyện bằng ml/train_model.py, ml/train_du_bao_gio.py")
    else:
        import warnings
        try:
            import joblib
        except ImportError:
            loi("Thiếu joblib"); return
        hong = []
        for f in tep:
            try:
                with warnings.catch_warnings(record=True) as w:
                    warnings.simplefilter("always")
                    joblib.load(f)
                if any("InconsistentVersion" in type(x.message).__name__ for x in w):
                    canh_bao(f"{f.name}: huấn luyện bằng phiên bản scikit-learn khác — nên cài đúng requirements.txt")
            except Exception as e:
                hong.append(f"{f.name} ({type(e).__name__})")
        if hong:
            loi("Không nạp được: " + ", ".join(hong) + " → cài đúng phiên bản thư viện hoặc huấn luyện lại")
        else:
            ok(f"Nạp được {len(tep)} tệp mô hình")
    fe = GOC / "frontend"
    (ok if (fe / "tong-quan.html").exists() else loi)(f"Thư mục web {'đủ' if (fe / 'tong-quan.html').exists() else 'THIẾU'} ({len(list(fe.glob('*.html')))} trang)")


def main():
    ap = argparse.ArgumentParser(description="Kiểm tra môi trường chạy AirHCM")
    ap.add_argument("--tao-csdl", action="store_true", help="tạo CSDL và bật PostGIS nếu chưa có")
    a = ap.parse_args()
    print(f"Kiểm tra môi trường AirHCM — {GOC}")
    kiem_he_thong()
    kiem_thu_vien()
    doc_env()
    kiem_csdl(a.tao_csdl)
    kiem_mo_hinh()
    print(f"\nKết quả: {len(LOI)} lỗi, {len(CANH_BAO)} cảnh báo.")
    print("=> SẴN SÀNG CHẠY" if not LOI else "=> Hãy sửa các mục [LỖI] ở trên rồi chạy lại.")
    return 1 if LOI else 0


if __name__ == "__main__":
    sys.exit(main())
