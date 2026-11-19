"""Chạy các notebook phân tích (code bài Lab01, Lab03 môn Python cho Máy học — chỉ đổi dữ liệu đầu vào)
rồi xuất biểu đồ lên web (trang Phương pháp).

Chạy từ thư mục gốc dự án:
    python ml/notebooks/xuat_bieu_do.py            # chạy lại notebook + xuất ảnh
    python ml/notebooks/xuat_bieu_do.py --khong-chay  # chỉ xuất ảnh từ notebook đã chạy

Cần thư viện: pip install -r ml/notebooks/requirements-notebook.txt
Kết quả:
    ml/notebooks/*.ipynb            notebook đã chạy, có sẵn biểu đồ (mở bằng Jupyter / VS Code)
    frontend/hinh/ml/*.png          biểu đồ ở các ô được gắn tag "web"
    frontend/hinh/ml/danh_sach.json danh sách biểu đồ + chỉ số đánh giá cho trang Phương pháp
"""

import argparse
import base64
import json
import sys
from datetime import datetime
from pathlib import Path

THU_MUC = Path(__file__).resolve().parent
GOC = THU_MUC.parent.parent
DICH = GOC / "frontend" / "hinh" / "ml"
NOTEBOOK = ["Lab01_PM25_HCM.ipynb", "Lab02_PM25_HCM.ipynb", "Lab03_PM25_HCM.ipynb"]


def sua_prophet_windows() -> None:
    """Windows: Prophet gọi prophet_model.bin cần tbb.dll của chính nó. Khi đường dẫn có ký tự Unicode
    (vd. 'Máy tính') hoặc máy có sẵn C:\\Windows\\System32\\tbb.dll, Windows nạp nhầm DLL khác phiên bản
    → lỗi 0xC0000139. Chép tbb.dll đúng phiên bản ra cạnh prophet_model.bin (Windows ưu tiên thư mục của tệp chạy)."""
    if sys.platform != "win32":
        return
    try:
        import prophet
    except ImportError:
        return
    import shutil
    goc_sm = Path(prophet.__file__).parent / "stan_model"
    dich = goc_sm / "tbb.dll"
    if dich.exists():
        return
    for nguon in goc_sm.rglob("tbb.dll"):
        shutil.copy2(nguon, dich)
        print(f"Đã chép {nguon.name} ra cạnh prophet_model.bin (sửa lỗi Prophet trên Windows)")
        return


def chay(ten: str) -> None:
    import nbformat
    from nbclient import NotebookClient

    duong = THU_MUC / ten
    nb = nbformat.read(duong, as_version=4)
    print(f"Đang chạy {ten} ...", flush=True)
    NotebookClient(nb, timeout=1800, kernel_name="python3",
                   resources={"metadata": {"path": str(THU_MUC)}}).execute()
    nbformat.write(nb, duong)


def xuat(ten: str) -> list[dict]:
    nb = json.loads((THU_MUC / ten).read_text(encoding="utf-8"))
    ds = []
    for c in nb["cells"]:
        web = c.get("metadata", {}).get("web")
        if c["cell_type"] != "code" or not web:
            continue
        anh = [o["data"]["image/png"] for o in c.get("outputs", []) if "image/png" in o.get("data", {})]
        if not anh:
            print(f"  ! Ô '{web['id']}' chưa có biểu đồ (notebook chưa chạy?)")
            continue
        png = anh[-1] if isinstance(anh[-1], str) else "".join(anh[-1])
        (DICH / f"{web['id']}.png").write_bytes(base64.b64decode(png))
        ds.append({**web, "anh": f"hinh/ml/{web['id']}.png", "notebook": f"ml/notebooks/{ten}"})
    return ds


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--khong-chay", action="store_true", help="Không chạy lại notebook, chỉ xuất ảnh")
    a = ap.parse_args()

    DICH.mkdir(parents=True, exist_ok=True)
    if not a.khong_chay:
        sua_prophet_windows()
        for ten in NOTEBOOK:
            chay(ten)

    bieu_do = []
    for ten in NOTEBOOK:
        bieu_do += xuat(ten)

    chi_so = {}
    for k in ("lab01", "lab02", "lab03"):
        f = THU_MUC / "ket_qua" / f"{k}_chi_so.json"
        if f.exists():
            chi_so[k] = json.loads(f.read_text(encoding="utf-8"))

    (DICH / "danh_sach.json").write_text(json.dumps({
        "cap_nhat": datetime.now().isoformat(timespec="seconds"),
        "nguon": "Code bài Lab01 (Hồi quy), BTTH2/Lab02 (Phân loại), BTTH3/Lab03 (Chuỗi thời gian) môn Python cho Máy học; dữ liệu du_lieu/gio_cache.csv (TP.HCM)",
        "bieu_do": bieu_do,
        "chi_so": chi_so,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Đã xuất {len(bieu_do)} biểu đồ vào {DICH.relative_to(GOC)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
