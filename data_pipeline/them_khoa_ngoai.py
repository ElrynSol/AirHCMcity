"""Thêm khóa ngoại (FOREIGN KEY) cho CSDL để sơ đồ ERD trong pgAdmin hiện đường nối.

Vì sao cần: các bảng dữ liệu hiện khai báo cột tram_id là INTEGER THƯỜNG, không có ràng buộc
khóa ngoại tới tram_quan_trac(id). pgAdmin chỉ vẽ đường quan hệ khi có FK thật, nên ERD đang
không có đường nối. Script này thêm FK một cách AN TOÀN:
  1. Bỏ qua nếu khóa ngoại đã tồn tại (chạy lại nhiều lần không sao).
  2. KIỂM TRA dữ liệu mồ côi (tram_id không có trong tram_quan_trac) TRƯỚC khi thêm.
     Nếu còn mồ côi, script KHÔNG thêm FK và báo rõ, tránh làm hỏng dữ liệu.
  3. Chỉ thêm FK khi dữ liệu sạch.

Chạy từ THƯ MỤC GỐC dự án:
    python data_pipeline/them_khoa_ngoai.py            # kiểm tra + thêm FK nếu dữ liệu sạch
    python data_pipeline/them_khoa_ngoai.py --chi-kiem-tra   # chỉ kiểm tra, không thay đổi gì
    python data_pipeline/them_khoa_ngoai.py --xoa-mo-coi     # XÓA các dòng mồ côi rồi thêm FK (cân nhắc kỹ)

Sau khi chạy xong, mở lại ERD Tool trong pgAdmin (kéo đủ các bảng vào) sẽ thấy đường quan hệ 1–n.
"""

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

GOC = Path(__file__).resolve().parent.parent
load_dotenv(GOC / ".env")

# Mỗi dòng: (bảng con, cột khóa ngoại, bảng cha, cột cha, tên ràng buộc)
KHOA_NGOAI = [
    ("du_lieu_tram_mat_dat", "tram_id", "tram_quan_trac", "id", "fk_matdat_tram"),
    ("du_lieu_gee_tphcm",    "tram_id", "tram_quan_trac", "id", "fk_gee_tram"),
    ("dang_ky_canh_bao",     "tram_id", "tram_quan_trac", "id", "fk_dangky_tram"),
]


def tao_engine():
    url = os.getenv("DATABASE_URL")
    if not url:
        g = os.getenv
        url = (f"postgresql://{g('DB_USER')}:{quote_plus(g('DB_PASS') or '')}"
               f"@{g('DB_HOST')}:{g('DB_PORT')}/{g('DB_NAME')}")
    return create_engine(url)


def bang_ton_tai(conn, bang):
    return conn.execute(text("SELECT to_regclass(:t)"), {"t": bang}).scalar() is not None


def fk_da_co(conn, bang, ten_rb):
    return conn.execute(text("""
        SELECT 1 FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.contype = 'f' AND t.relname = :bang AND c.conname = :ten
    """), {"bang": bang, "ten": ten_rb}).first() is not None


def dem_mo_coi(conn, bang_con, cot, bang_cha, cot_cha):
    return conn.execute(text(f"""
        SELECT COUNT(*) FROM {bang_con} c
        LEFT JOIN {bang_cha} p ON c.{cot} = p.{cot_cha}
        WHERE c.{cot} IS NOT NULL AND p.{cot_cha} IS NULL
    """)).scalar()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chi-kiem-tra", action="store_true", help="chỉ kiểm tra, không thay đổi CSDL")
    ap.add_argument("--xoa-mo-coi", action="store_true", help="xóa các dòng mồ côi trước khi thêm FK")
    a = ap.parse_args()

    engine = tao_engine()
    them, bo_qua, vuong = 0, 0, 0

    with engine.begin() as conn:
        for bang_con, cot, bang_cha, cot_cha, ten_rb in KHOA_NGOAI:
            print(f"\n• {bang_con}.{cot} → {bang_cha}.{cot_cha}  (ràng buộc {ten_rb})")

            if not bang_ton_tai(conn, bang_con) or not bang_ton_tai(conn, bang_cha):
                print("  ⚠ Bỏ qua: bảng chưa tồn tại trong CSDL.")
                bo_qua += 1
                continue

            if fk_da_co(conn, bang_con, ten_rb):
                print("  ✓ Khóa ngoại đã có từ trước — bỏ qua.")
                bo_qua += 1
                continue

            mo_coi = dem_mo_coi(conn, bang_con, cot, bang_cha, cot_cha)
            if mo_coi > 0:
                print(f"  ✗ Có {mo_coi} dòng mồ côi (tram_id không tồn tại trong {bang_cha}).")
                if a.xoa_mo_coi and not a.chi_kiem_tra:
                    n = conn.execute(text(f"""
                        DELETE FROM {bang_con} c
                        WHERE c.{cot} IS NOT NULL
                          AND NOT EXISTS (SELECT 1 FROM {bang_cha} p WHERE p.{cot_cha} = c.{cot})
                    """)).rowcount
                    print(f"    → Đã xóa {n} dòng mồ côi.")
                else:
                    print("    → Chưa thêm FK. Chạy lại với --xoa-mo-coi để xóa các dòng này, "
                          "hoặc kiểm tra lại dữ liệu trước.")
                    vuong += 1
                    continue

            if a.chi_kiem_tra:
                print("  (chế độ chỉ kiểm tra: dữ liệu sạch, sẵn sàng thêm FK — chưa thực hiện)")
                continue

            conn.execute(text(
                f"ALTER TABLE {bang_con} ADD CONSTRAINT {ten_rb} "
                f"FOREIGN KEY ({cot}) REFERENCES {bang_cha}({cot_cha})"
            ))
            print("  ✓ Đã thêm khóa ngoại.")
            them += 1

    print(f"\nTóm tắt: thêm {them}, bỏ qua {bo_qua}, vướng dữ liệu mồ côi {vuong}.")
    if vuong:
        print("Còn bảng vướng dữ liệu mồ côi — xử lý xong rồi chạy lại để thêm nốt FK.")
    elif not a.chi_kiem_tra:
        print("Xong. Mở lại ERD Tool trong pgAdmin (kéo đủ các bảng) để thấy đường quan hệ.")


if __name__ == "__main__":
    main()
