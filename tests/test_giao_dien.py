"""Kiểm thử giao diện tĩnh (không cần trình duyệt, không cần máy chủ) + cách tính điểm SUS của trang khảo sát.

- Mỗi trang HTML: JavaScript nội tuyến không lỗi cú pháp (dùng `node --check` nếu máy có Node.js, không có thì bỏ qua).
- Liên kết nội bộ (href/src tới tệp .html/.js/.css cùng thư mục) trỏ tới tệp có thật.
- Không còn tham chiếu tới chức năng đã gỡ (IoT/MQTT) và không gọi cứng http://localhost:8000.
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

GOC = Path(__file__).resolve().parent.parent
FE = GOC / "frontend"
sys.path.insert(0, str(GOC / "backend"))
TRANG = sorted(FE.glob("*.html"))


@pytest.mark.parametrize("trang", TRANG, ids=lambda p: p.name)
def test_lien_ket_noi_bo_ton_tai(trang):
    s = trang.read_text(encoding="utf-8")
    hong = []
    for duong in re.findall(r'(?:href|src)="([^"#?:]+\.(?:html|js|css))(?:[#?][^"]*)?"', s):
        if not duong.startswith(("http", "//", "/api")) and not (FE / duong).exists():
            hong.append(duong)
    assert not hong, f"{trang.name}: liên kết hỏng {hong}"


@pytest.mark.parametrize("trang", TRANG, ids=lambda p: p.name)
def test_khong_con_iot_va_localhost(trang):
    s = trang.read_text(encoding="utf-8")
    assert not re.search(r"iot\.html|iot-layer\.js|/api/v1/iot", s), f"{trang.name} còn tham chiếu IoT đã gỡ"
    assert "http://localhost:8000/api" not in s, f"{trang.name} gọi cứng localhost:8000 (hỏng khi chạy qua tên miền)"


@pytest.mark.skipif(shutil.which("node") is None, reason="máy không có Node.js")
@pytest.mark.parametrize("trang", TRANG, ids=lambda p: p.name)
def test_javascript_noi_tuyen_dung_cu_phap(trang):
    s = trang.read_text(encoding="utf-8")
    khoi = re.findall(r"<script>(.*?)</script>", s, flags=re.S)       # chỉ khối nội tuyến (không có thuộc tính src)
    if not khoi:
        return
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write("\n;\n".join(khoi))
    try:
        r = subprocess.run(["node", "--check", f.name], capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert r.returncode == 0, f"{trang.name}: {r.stderr[:400]}"
    finally:
        Path(f.name).unlink(missing_ok=True)


def test_menu_tro_toi_trang_co_that():
    s = (FE / "nav.js").read_text(encoding="utf-8")
    for t in re.findall(r"'([a-z0-9-]+\.html)'", s):
        assert (FE / t).exists(), f"menu trỏ tới {t} không tồn tại"


def test_diem_sus_theo_cong_thuc_brooke():
    from services.khao_sat import diem_sus, xep_hang, tong_hop_tu
    assert diem_sus([5, 1, 5, 1, 5, 1, 5, 1, 5, 1]) == 100.0
    assert diem_sus([1, 5, 1, 5, 1, 5, 1, 5, 1, 5]) == 0.0
    assert diem_sus([3] * 10) == 50.0
    assert xep_hang(85) .startswith("A") and xep_hang(68).startswith("C") and xep_hang(40).startswith("F")
    with pytest.raises(ValueError):
        diem_sus([6, 1, 1, 1, 1, 1, 1, 1, 1, 1])
    th = tong_hop_tu([("sinh_vien", [5, 1] * 5, 100.0), ("nguoi_dan", [3] * 10, 50.0)])
    assert th["so_phieu"] == 2 and th["sus_tb"] == 75.0 and th["ci95"][0] < 75 < th["ci95"][1]
