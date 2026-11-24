"""Tạo bản nộp gọn (.zip) của đồ án: chỉ mã nguồn, tài liệu, mô hình đã huấn luyện và APK.
Bỏ môi trường ảo, thư viện tải về, file build, bộ nhớ đệm, nhật ký và MỌI file bí mật.
Trước khi nén, quét toàn bộ file sẽ nộp: nếu thấy giá trị bí mật trong .env (khóa API, mật khẩu...) thì DỪNG, không tạo zip.

Chạy từ bất kỳ đâu:
    python dong_goi/tao_ban_nop.py                  # tạo ../AirHCM_1250080037_<ngày>.zip (cạnh thư mục dự án)
    python dong_goi/tao_ban_nop.py --thu            # chỉ liệt kê, không tạo zip
    python dong_goi/tao_ban_nop.py --khong-mo-hinh  # bỏ models/ (nhẹ hơn ~28 MB, phải huấn luyện lại mới chạy dự báo)
    python dong_goi/tao_ban_nop.py --khong-apk      # bỏ mobile/AirHCM.apk
    python dong_goi/tao_ban_nop.py --kiem-thu       # chạy toàn bộ kiểm thử tự động (228 ca) trước; có lỗi thì không đóng gói
Trong zip có MUC_LUC.txt: phiên bản, ngày tạo, danh sách tệp kèm SHA-256 (kiểm tra bản nộp không bị sửa/hỏng).
Zip vừa tạo được mở lại và kiểm tra CRC từng tệp. Chỉ dùng thư viện chuẩn của Python.
"""
import argparse, datetime, hashlib, re, subprocess, sys, zipfile
from collections import Counter
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent
TEN_GOC = "AirHCM"   # thư mục gốc bên trong file zip
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # cửa sổ lệnh Windows dùng bảng mã cũ vẫn in được tiếng Việt
    except Exception:
        pass

# Thư mục bỏ qua ở MỌI cấp: tạo lại được bằng lệnh (venv, npm install, build) hoặc chỉ là rác máy
THU_MUC_BO = {"venv", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".git", ".idea", ".vscode",
              "mlruns", ".gradle", "build", ".ipynb_checkpoints"}
DUONG_DAN_BO = {"tools/cu",            # công cụ cũ dùng một lần (đã chuyển ra kho lưu trữ; giữ để an toàn)
                "bi_mat", "bi_mat_may_chu",   # khóa VAPID (thông báo đẩy), khóa GEE trên máy chủ
                "sao_luu",             # bản sao lưu CSDL (có dữ liệu tài khoản)
                "ml/notebooks/data"}   # dữ liệu ngày do notebook tự tạo lại từ du_lieu/gio_cache.csv
# File bí mật / dữ liệu cá nhân / nhật ký máy
TEP_BO = {".env", "gee-key.json", "backup.sql", "mlflow.db", "log_dong_bo.txt", "local.properties", ".dong_bo.lock",
          "Bao_cao_Do_an_Chuyen_nganh_AirHCM_1250080037.docx",
          "Bao_cao_AirHCM_DaSua_MoDau_Chuong1.docx"}   # bản nháp báo cáo cũ (báo cáo nộp riêng ở thư mục 01_Bao_cao)
DUOI_BO = {".pyc", ".log", ".sql", ".gz", ".pem", ".key", ".keystore", ".jks"}

DUOI_VAN_BAN = {".py", ".js", ".html", ".css", ".md", ".txt", ".json", ".toml", ".yml", ".yaml", ".bat", ".ps1",
                ".ino", ".xml", ".gradle", ".properties", ".webmanifest", ".svg", ".csv", ".example", ""}
MAU_BI_MAT = [   # dấu hiệu khóa thường gặp, phòng khi .env không có sẵn để đối chiếu
    ("khóa Google API", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("khóa Anthropic", re.compile(r"sk-ant-[0-9A-Za-z_\-]{20,}")),
    ("khóa riêng (private key)", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]


def bi_bo(rel: Path, khong_mo_hinh: bool, khong_apk: bool) -> bool:
    s = rel.as_posix()
    if any(p in THU_MUC_BO for p in rel.parts[:-1]) or any(s == d or s.startswith(d + "/") for d in DUONG_DAN_BO):
        return True
    ten = rel.name
    if s.startswith("backend/sql/") and rel.suffix.lower() == ".sql":
        return False   # cấu trúc bảng (không chứa dữ liệu) – máy chủ cần để tạo CSDL mới
    if ten in TEP_BO or (ten.startswith(".env.") and ten != ".env.example") or rel.suffix.lower() in DUOI_BO:
        return True
    if rel.parts[0] == "models" and ten.startswith("downscale_"):
        return True   # mô hình thử nghiệm cũ, máy chủ không dùng
    if khong_mo_hinh and rel.parts[0] == "models":
        return True
    return khong_apk and rel.suffix.lower() == ".apk"


def gia_tri_bi_mat() -> dict:
    """Các giá trị nhạy cảm trong .env (tên biến có KEY/PASS/SECRET/TOKEN) để đối chiếu; không in ra giá trị."""
    env = GOC / ".env"
    kq = {}
    if env.exists():
        for dong in env.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "=" in dong and not dong.lstrip().startswith("#"):
                ten, gt = dong.split("=", 1)
                gt = gt.strip().strip('"').strip("'")
                ten_hoa = ten.strip().upper()
                if (re.search(r"KEY|PASS|SECRET|TOKEN", ten_hoa) and not ten_hoa.endswith(("_FILE", "_PATH"))
                        and len(gt) >= 8):   # GEE_KEY_FILE chỉ là TÊN file khóa, không phải bí mật
                    kq[ten.strip()] = gt
    return kq


def quet_bi_mat(ds: list) -> list:
    bi_mat, loi = gia_tri_bi_mat(), []
    for f in ds:
        if f.suffix.lower() not in DUOI_VAN_BAN or f.stat().st_size > 5_000_000:
            continue
        nd = f.read_text(encoding="utf-8", errors="ignore")
        rel = f.relative_to(GOC).as_posix()
        loi += [f"{rel}: chứa giá trị của biến {ten} trong .env" for ten, gt in bi_mat.items() if gt in nd]
        loi += [f"{rel}: có dạng {mo_ta}" for mo_ta, mau in MAU_BI_MAT if mau.search(nd)]
    return loi


def phien_ban() -> str:
    m = re.findall(r"^## (v[\d.]+)", (GOC / "README.md").read_text(encoding="utf-8"), re.M)
    return m[-1] if m else "?"


def muc_luc(ds: list, tong: int) -> str:
    """Danh sách tệp nộp kèm kích thước và SHA-256: hội đồng/giảng viên đối chiếu được bản nộp còn nguyên vẹn."""
    dong = [f"AirHCM — Hệ thống Giám sát & Dự báo Chất lượng Không khí TP.HCM · {phien_ban()}",
            "Lê Ngọc Ánh Dương (MSSV 1250080037) · GVHD: TS. Dương Thị Thúy Nga",
            f"Tạo lúc {datetime.datetime.now():%d/%m/%Y %H:%M} · {len(ds)} tệp · {tong / 1e6:.1f} MB (chưa nén)",
            "Cài đặt: xem README.md mục Chạy · Cấu trúc: docs/CAU_TRUC_DU_AN.md", "",
            f"{'Kích thước':>12}  {'SHA-256 (16 ký tự đầu)':<18}  Tệp"]
    for f in ds:
        h = hashlib.sha256(f.read_bytes()).hexdigest()[:16]
        dong.append(f"{f.stat().st_size:>12,}  {h:<18}  {f.relative_to(GOC).as_posix()}")
    return "\n".join(dong) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ra", help="đường dẫn file zip (mặc định: cạnh thư mục dự án)")
    ap.add_argument("--thu", action="store_true", help="chỉ liệt kê, không tạo zip")
    ap.add_argument("--khong-mo-hinh", action="store_true")
    ap.add_argument("--khong-apk", action="store_true")
    ap.add_argument("--kiem-thu", action="store_true", help="chạy pytest trước khi đóng gói")
    a = ap.parse_args()

    ds = sorted(f for f in GOC.rglob("*") if f.is_file()
                and not bi_bo(f.relative_to(GOC), a.khong_mo_hinh, a.khong_apk))
    tong = sum(f.stat().st_size for f in ds)
    theo_muc = Counter()
    for f in ds:
        rel = f.relative_to(GOC)
        theo_muc[rel.parts[0] + ("/" if len(rel.parts) > 1 else "")] += f.stat().st_size
    print(f"{len(ds)} file, {tong / 1e6:.1f} MB (chưa nén)")
    for muc, kt in sorted(theo_muc.items(), key=lambda x: -x[1]):
        print(f"  {muc:<32}{kt / 1e6:8.2f} MB")

    loi = quet_bi_mat(ds)
    if loi:
        print("\nDỪNG: phát hiện thông tin bí mật trong file sẽ nộp:")
        print("\n".join("  - " + x for x in loi))
        sys.exit(1)
    print("\nĐã quét bí mật: không thấy khóa API / mật khẩu trong các file sẽ nộp.")
    if a.thu:
        return

    if a.kiem_thu:
        print("\nChạy kiểm thử tự động (khoảng 1 phút)...")
        kq = subprocess.run([sys.executable, "-m", "pytest", "../tests", "-q", "-p", "no:cacheprovider"], cwd=GOC / "backend",
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
        dong = [d for d in kq.stdout.splitlines() if d.strip()]
        print("  " + (dong[-1] if dong else "không có kết quả"))
        if kq.returncode != 0:
            print("DỪNG: kiểm thử chưa đạt, không tạo bản nộp."); sys.exit(1)

    ra = Path(a.ra) if a.ra else GOC.parent / f"AirHCM_1250080037_{datetime.date.today():%Y%m%d}.zip"
    with zipfile.ZipFile(ra, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in ds:
            ten = f"{TEN_GOC}/{f.relative_to(GOC).as_posix()}"
            if f.suffix == ".sh":   # giữ quyền chạy khi giải nén trên Linux/macOS (unzip đọc quyền Unix trong zip)
                zi = zipfile.ZipInfo.from_file(f, ten)
                zi.external_attr = (0o100755 << 16)
                zi.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(zi, f.read_bytes())
            else:
                z.write(f, ten)
        z.writestr(f"{TEN_GOC}/MUC_LUC.txt", muc_luc(ds, tong))
    with zipfile.ZipFile(ra) as z:   # mở lại, kiểm tra CRC từng tệp
        hong = z.testzip()
        so = len(z.namelist())
    if hong:
        print(f"LỖI: tệp {hong} trong zip bị hỏng — hãy tạo lại."); sys.exit(1)
    print(f"Đã tạo {ra} ({ra.stat().st_size / 1e6:.1f} MB, {so} tệp, đã kiểm tra toàn vẹn)")


if __name__ == "__main__":
    main()
