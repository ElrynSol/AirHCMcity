"""Kiểm thử hồ sơ phương pháp (core/phuong_phap.py) và đánh giá nội suy (ml/danh_gia_noi_suy.py).

Mục đích: những gì trang Phương pháp và báo cáo trình bày (mô hình, đặc trưng, độ phân giải, quy tắc kết luận)
phải khớp với mô hình đang chạy thật, không phải con số ghi tay.
"""
import pandas as pd
import pytest

from core import phuong_phap as pp


def test_quy_tac_ket_luan():
    assert pp.ket_luan(0.07, 0.03, 0.10) == "dat"            # cả khoảng tin cậy > 0
    assert pp.ket_luan(0.05, -0.1, 0.2) == "tham_khao"       # dương nhưng khoảng chứa 0
    assert pp.ket_luan(-0.04, -0.1, 0.01) == "chua_dat"
    assert pp.ket_luan(0.2) == "chua_kiem_dinh"               # chưa có khoảng tin cậy
    assert pp.ket_luan(None) == "chua_kiem_dinh"


def test_moi_ket_luan_deu_co_dien_giai():
    for m in pp.tong_hop()["mo_hinh"]:
        d = m["danh_gia"]
        if d and d["ket_luan"] != "thuc_nghiem":
            assert d["ket_luan"] in pp.TIEU_CHI


def test_moi_mo_hinh_khai_bao_day_du():
    can = {"ma", "chi_so", "tam", "nhom", "do_phan_giai_ra", "mo_hinh", "doi_chung", "du_lieu", "api", "trang", "ma_nguon"}
    ma = [m["ma"] for m in pp.MO_HINH]
    assert len(ma) == len(set(ma))
    for m in pp.MO_HINH:
        assert can <= set(m), m["ma"]
    # đủ các tầm dự báo: giờ, ngày, tháng; đủ 3 chất có nồng độ mặt đất
    tam = " ".join(m["tam"] for m in pp.MO_HINH)
    assert "giờ" in tam and "Ngày mai" in tam and "tháng" in tam
    chat = " ".join(m["chi_so"] for m in pp.MO_HINH)
    assert "PM2.5" in chat and "PM10" in chat and "O3" in chat


def test_tep_ma_nguon_khai_bao_ton_tai():
    goc = pp.config.PROJECT_ROOT
    for m in pp.MO_HINH:
        for t in m["ma_nguon"].split(","):
            assert (goc / t.strip()).exists(), t
    for n in pp.NGUON:
        assert (goc / n["ma_nguon"]).exists(), n["ma_nguon"]
    for b in pp.BUOC_TICH_HOP:
        t = b["ma_nguon"]
        assert (goc / t).exists() or (goc / "backend" / t).exists(), t


def test_dac_trung_khop_mo_hinh_dang_chay():
    """Danh sách đặc trưng trang Phương pháp hiển thị phải trùng với mô hình đã lưu."""
    from services.du_bao_gio import DAC_TRUNG
    import du_bao_da_chat
    import mo_hinh_tram_that
    tra = {m["ma"]: m for m in pp.tong_hop()["mo_hinh"]}
    assert tra["gio"]["dac_trung"] == list(DAC_TRUNG)
    assert tra["pm25_ngay"]["dac_trung"] == list(du_bao_da_chat.DAC_TRUNG)
    assert tra["tram_that"]["dac_trung"] == list(mo_hinh_tram_that.DAC_TRUNG)
    if (pp.THU_MUC / "model_metadata.pkl").exists():
        import joblib
        meta = joblib.load(pp.THU_MUC / "model_metadata.pkl")
        assert tra["ngay_mai"]["dac_trung"] == list(meta["features_du_bao_ngay_mai"])


def test_chi_so_doc_tu_tep_ket_qua():
    """Các con số đánh giá lấy đúng từ tệp kết quả (không ghi tay)."""
    import json
    f = pp.THU_MUC / "du_bao_da_chat.json"
    if not f.exists():
        pytest.skip("chưa huấn luyện mô hình đa chất")
    d = json.loads(f.read_text(encoding="utf-8"))["chat"]["pm10"]
    m = d["mo_hinh"][d["mo_hinh_chon"]]
    cs = pp.cs_da_chat("pm10")
    assert cs["ky_nang"] == round(m["ky_nang"], 3) and cs["so_mau_kiem_tra"] == d["so_ngay_kiem_tra"]
    assert cs["ket_luan"] == pp.ket_luan(m["ky_nang"], m["ky_nang_ci95"]["thap"], m["ky_nang_ci95"]["cao"])


def test_tong_hop_du_bon_phan():
    d = pp.tong_hop()
    assert {"mo_hinh", "nguon", "chuoi_do_phan_giai", "tich_hop", "quy_trinh_danh_gia", "tieu_chi"} <= set(d)
    assert len(d["chuoi_do_phan_giai"]) == 4
    ma_nguon = {n["ma"] for n in d["nguon"]}
    assert {"cams", "era5", "s5p", "openaq"} <= ma_nguon


def test_gop_o_luoi_chong_lac_quan_gia_tao():
    """Hai điểm cùng ô lưới (cùng giá trị) được gộp thành một trước khi kiểm chéo bỏ một điểm."""
    from danh_gia_noi_suy import gop_theo_o_luoi
    g = pd.DataFrame({"pm25_mean": [20.0, 20.0, 30.0, 40.0], "lat": [10.0, 10.2, 10.5, 11.0], "lon": [106.0, 106.0, 106.5, 107.0]})
    o = gop_theo_o_luoi(g)
    assert len(o) == 3
    assert abs(o.loc[o["pm25_mean"] == 20.0, "lat"].iloc[0] - 10.1) < 1e-9


def test_api_phuong_phap():
    from starlette.testclient import TestClient
    from main import app
    r = TestClient(app, base_url="http://testserver").get("/api/v1/phuong-phap")
    assert r.status_code == 200
    j = r.json()
    assert len(j["mo_hinh"]) == len(pp.MO_HINH) and j["nguon"]
