"""Kiểm thử Trợ lý AirHCM (không gọi API thật, không cần CSDL):
- chế độ tự động: nhận diện ý định, trả lời bằng số liệu được truyền vào
- làm sạch lịch sử hội thoại, giới hạn tần suất / hạn mức AI
- chế độ AI với client giả lập: trả lời bình thường, bị từ chối, lỗi trước khi có chữ, lỗi giữa chừng

Chạy từ thư mục gốc:  python -m pytest tests/test_tro_ly.py -q
"""
import asyncio
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from services import tro_ly

DU_LIEU = {
    "cap_nhat": "2026-10-23 14:00",
    "hien_tai": {"aqi": 112, "muc": "Kém", "chat": "PM2.5", "pm25": 45.0, "nguoi_binh_thuong": "Giảm hoạt động ngoài trời.",
                 "nhom_nhay_cam": "Nên giảm hoạt động mạnh.", "y_nghia": "..."},
    "nguong": {"who": 15, "qcvn": 50, "lan_who": 3.0, "phan_tram_qcvn": 90},
    "du_bao": {"gio": [{"gio": "2026-10-23T15:00", "pm25": 40.0, "aqi": 110}], "tb_24h_toi": 38.2, "aqi_cao_nhat": 118,
               "khung_tot": {"tu": "2026-10-24T10:00", "den": "2026-10-24T12:00", "pm25_tb": 27.1},
               "khung_xau": {"tu": "2026-10-24T05:00", "den": "2026-10-24T07:00", "pm25_tb": 50.0}, "so_gio_tren_who": 24},
    "xep_hang": [{"ma": "T11", "ten": "Vũng Tàu", "aqi": 48, "muc": "Tốt", "pm25": 19.0},
                 {"ma": "T01", "ten": "Sài Gòn", "aqi": 85, "muc": "Trung bình", "pm25": 42.5},
                 {"ma": "T16", "ten": "Bình Chánh", "aqi": 124, "muc": "Kém", "pm25": 55.0}],
    "thoi_tiet": {"nhiet_do": 31.4, "cam_giac": 39.0, "do_am": 69, "gio_kmh": 2.5, "mua_mm": 0, "mo_ta": "Trời quang", "bieu_tuong": "☀️", "luc": "2026-10-23 13:45"},
    "xu_huong": [{"ngay": "2026-10-22", "aqi": 67}], "iot": None,
}


# ---------- Chế độ tự động ----------
@pytest.mark.parametrize("cau_hoi, phai_co", [
    ("Hôm nay có nên chạy bộ không?", ["**112**", "10:00–12:00"]),
    ("Khu vực nào đang SẠCH NHẤT?", ["T11", "T16"]),
    ("Tối nay không khí thế nào", ["38,2", "05:00–07:00"]),
    ("có cần đeo khẩu trang ko", ["N95"]),
    ("AQI là gì?", ["QĐ 1459", "Nguy hại"]),
    ("trẻ em có sao không", ["Nên giảm hoạt động mạnh."]),
    ("thời tiết hôm nay", ["31°C"]),
    ("số liệu có chính xác không", ["CAMS"]),
    ("viết thơ tình", ["**112**", "Bạn có thể hỏi"]),
])
def test_tra_loi_tu_dong(cau_hoi, phai_co):
    tl = tro_ly.tra_loi_tu_dong(cau_hoi, DU_LIEU)
    for s in phai_co:
        assert s in tl


def test_tra_loi_tu_dong_khi_thieu_du_lieu():
    tl = tro_ly.tra_loi_tu_dong("dự báo ngày mai", {"hien_tai": {}})
    assert "Chưa có dự báo" in tl


def test_khoi_du_lieu_on_dinh_va_gon():
    a, b = tro_ly.khoi_du_lieu(DU_LIEU), tro_ly.khoi_du_lieu(dict(DU_LIEU))
    assert a == b and a.startswith("<du_lieu>") and '"aqi":112' in a


# ---------- Lịch sử, giới hạn ----------
def test_lam_sach_lich_su():
    ls = [{"vai": "assistant", "noi_dung": "chào"}, {"vai": "user", "noi_dung": "a"}, {"vai": "user", "noi_dung": "trùng vai"},
          {"vai": "assistant", "noi_dung": "b" * 3000}, {"vai": "hacker", "noi_dung": "x"}, {"vai": "user", "noi_dung": "câu cuối"}]
    out = tro_ly.lam_sach_lich_su(ls)
    assert [m["role"] for m in out] == ["user", "assistant"]
    assert len(out[1]["content"]) == 1500
    assert tro_ly.lam_sach_lich_su(None) == []


def test_gioi_han_theo_ip_va_han_muc_ai(monkeypatch):
    monkeypatch.setattr(tro_ly, "_theo_ip", {})
    monkeypatch.setattr(tro_ly, "_toan_he_thong", __import__("collections").deque())
    monkeypatch.setattr(tro_ly, "GIOI_HAN_IP", 3)
    monkeypatch.setattr(tro_ly, "GIOI_HAN_GIO", 2)
    kq = [tro_ly.kiem_tra_gioi_han("1.1.1.1", True, now=100 + i) for i in range(4)]
    assert [k[0] for k in kq] == [True, True, True, False]            # câu thứ 4 trong 10 phút bị chặn
    assert [k[1] for k in kq[:3]] == [True, True, False]               # hết hạn mức AI → trả lời tự động
    assert tro_ly.kiem_tra_gioi_han("1.1.1.1", True, now=100 + 700)[0] # sau 10 phút được hỏi lại


# ---------- Chế độ AI với client giả lập ----------
class _LuongGia:
    def __init__(self, chu, stop_reason="end_turn", loi_sau=None):
        self._chu, self._stop, self._loi_sau = chu, stop_reason, loi_sau

    async def __aenter__(self):
        async def gen():
            for i, c in enumerate(self._chu):
                if self._loi_sau is not None and i == self._loi_sau:
                    raise anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
                yield c
        self.text_stream = gen()
        return self

    async def __aexit__(self, *a):
        return False

    async def get_final_message(self):
        return SimpleNamespace(stop_reason=self._stop, model="claude-opus-5-5",
                               usage=SimpleNamespace(input_tokens=1200, output_tokens=80, cache_read_input_tokens=0))


def _client_gia(luong, ghi):
    def stream(**kw):
        ghi.update(kw)
        return luong
    return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=stream)))


def _chay(gen):
    async def gom():
        return [x async for x in gen]
    return asyncio.run(gom())


def test_ai_tra_loi_binh_thuong(monkeypatch):
    ghi = {}
    monkeypatch.setattr(tro_ly, "_client", _client_gia(_LuongGia(["AQI ", "đang 112."]), ghi))
    ev = _chay(tro_ly.luong_ai("hỏi", [], DU_LIEU))
    assert [e for e, _ in ev] == ["chu", "chu", "xong"]
    assert ev[-1][1]["stop_reason"] == "end_turn" and ev[-1][1]["token"]["vao"] == 1200
    # tham số gửi đi: model, effort, dự phòng khi bị từ chối, dữ liệu nằm trong system
    assert ghi["model"] == tro_ly.MODEL and ghi["output_config"] == {"effort": tro_ly.EFFORT}
    assert ghi["fallbacks"] == "default" and ghi["betas"] == ["server-side-fallback-2026-07-01"]
    assert "<tai_lieu_du_an>" in ghi["system"][1]["text"] and "<du_lieu>" in ghi["system"][2]["text"] and ghi["messages"][-1] == {"role": "user", "content": "hỏi"}


def test_ai_bi_tu_choi(monkeypatch):
    monkeypatch.setattr(tro_ly, "_client", _client_gia(_LuongGia([], stop_reason="refusal"), {}))
    ev = _chay(tro_ly.luong_ai("hỏi", [], DU_LIEU))
    assert ev[0][0] == "chu" and "không thể trả lời" in ev[0][1]["t"]
    assert ev[-1][1]["stop_reason"] == "refusal"


def test_ai_loi_truoc_khi_co_chu_thi_nem_ra(monkeypatch):
    monkeypatch.setattr(tro_ly, "_client", _client_gia(_LuongGia(["a"], loi_sau=0), {}))
    with pytest.raises(anthropic.APIConnectionError):
        _chay(tro_ly.luong_ai("hỏi", [], DU_LIEU))


def test_ai_loi_giua_chung_thi_bao_loi(monkeypatch):
    monkeypatch.setattr(tro_ly, "_client", _client_gia(_LuongGia(["a", "b", "c"], loi_sau=2), {}))
    ev = _chay(tro_ly.luong_ai("hỏi", [], DU_LIEU))
    assert [e for e, _ in ev] == ["chu", "chu", "loi"]


# ---------- Gemini + kiến thức đồ án ----------
from google.genai import errors as g_errors  # noqa: E402


def test_chon_nha_cung_cap(monkeypatch):
    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "TRO_LY_AI"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(tro_ly, "NHA_CUNG_CAP", "auto")
    assert tro_ly.nha_cung_cap() is None
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert tro_ly.nha_cung_cap() == "claude"
    monkeypatch.setenv("GEMINI_API_KEY", "y")
    assert tro_ly.nha_cung_cap() == "gemini" and tro_ly.ten_model() == tro_ly.GEMINI_MODEL   # auto ưu tiên Gemini
    monkeypatch.setattr(tro_ly, "NHA_CUNG_CAP", "claude")
    assert tro_ly.nha_cung_cap() == "claude"
    monkeypatch.setenv("TRO_LY_AI", "0")
    assert tro_ly.nha_cung_cap() is None


def test_kien_thuc_du_an_doc_readme():
    k = tro_ly.kien_thuc_du_an()
    assert k.startswith("<tai_lieu_du_an>") and 'ten="README.md"' in k and 'ten="mobile/README_MOBILE.md"' in k
    assert "AIza" not in k and "sk-ant" not in k     # chỉ tài liệu, không lẫn khóa API


@pytest.mark.parametrize("cau_hoi", ["Kiến trúc hệ thống gồm những gì?", "đồ án dùng công nghệ gì", "cách chạy dự án"])
def test_tu_dong_cau_hoi_ve_do_an(cau_hoi):
    tl = tro_ly.tra_loi_tu_dong(cau_hoi, DU_LIEU)
    assert "FastAPI" in tl and "QĐ 1459" in tl


class _PhanGia:
    def __init__(self, text=None, finish=None, block=None, usage=None, thought=False):
        part = SimpleNamespace(text=text, thought=thought)
        self.candidates = [SimpleNamespace(finish_reason=SimpleNamespace(name=finish) if finish else None,
                                           content=SimpleNamespace(parts=[part] if text else []))] if (text or finish) else []
        self.prompt_feedback = SimpleNamespace(block_reason=SimpleNamespace(name=block)) if block else None
        self.usage_metadata = usage


def _gemini_gia(cac_phan, ghi, loi_sau=None):
    async def gen():
        for i, p in enumerate(cac_phan):
            if loi_sau is not None and i == loi_sau:
                raise g_errors.APIError(503, {"error": {"message": "unavailable", "status": "UNAVAILABLE"}})
            yield p

    async def generate_content_stream(**kw):
        ghi.update(kw)
        return gen()
    return SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content_stream=generate_content_stream)))


def test_gemini_tra_loi_binh_thuong(monkeypatch):
    ghi = {}
    u = SimpleNamespace(prompt_token_count=9000, candidates_token_count=120, cached_content_token_count=0)
    monkeypatch.setattr(tro_ly, "_gemini", _gemini_gia([_PhanGia("suy nghĩ", thought=True), _PhanGia("AQI "), _PhanGia("112.", "STOP", usage=u)], ghi))
    lich_su = [{"role": "user", "content": "chào"}, {"role": "assistant", "content": "chào bạn"}]
    ev = _chay(tro_ly.luong_ai("hỏi", lich_su, DU_LIEU, "gemini"))
    assert [e for e, _ in ev] == ["chu", "chu", "xong"]                     # phần "thought" không hiện ra
    assert ev[-1][1]["nha_cung_cap"] == "gemini" and ev[-1][1]["token"]["vao"] == 9000
    assert ghi["model"] == tro_ly.GEMINI_MODEL
    assert [c.role for c in ghi["contents"]] == ["user", "model", "user"]     # assistant → model
    si = ghi["config"].system_instruction
    assert "<tai_lieu_du_an>" in si and "<du_lieu>" in si


def test_gemini_bi_chan(monkeypatch):
    monkeypatch.setattr(tro_ly, "_gemini", _gemini_gia([_PhanGia(block="SAFETY")], {}))
    ev = _chay(tro_ly.luong_ai("hỏi", [], DU_LIEU, "gemini"))
    assert "không thể trả lời" in ev[0][1]["t"] and ev[-1][1]["stop_reason"] == "SAFETY"


def test_gemini_loi_truoc_va_giua_chung(monkeypatch):
    monkeypatch.setattr(tro_ly, "_gemini", _gemini_gia([_PhanGia("a")], {}, loi_sau=0))
    with pytest.raises(g_errors.APIError):
        _chay(tro_ly.luong_ai("hỏi", [], DU_LIEU, "gemini"))
    monkeypatch.setattr(tro_ly, "_gemini", _gemini_gia([_PhanGia("a"), _PhanGia("b")], {}, loi_sau=1))
    ev = _chay(tro_ly.luong_ai("hỏi", [], DU_LIEU, "gemini"))
    assert [e for e, _ in ev] == ["chu", "loi"]


# ---------- Chuỗi model Gemini dự phòng (hạn mức miễn phí theo từng model) ----------
def _loi_gemini(code, retry=None):
    chi_tiet = [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry}] if retry else []
    return g_errors.APIError(code, {"error": {"code": code, "message": "x", "status": "X", "details": chi_tiet}})


def _gemini_theo_model(loi_theo_model, ghi):
    async def generate_content_stream(**kw):
        ghi.append(kw["model"])
        if kw["model"] in loi_theo_model:
            raise loi_theo_model[kw["model"]]

        async def gen():
            yield _PhanGia("Trả lời từ " + kw["model"], "STOP")
        return gen()
    return SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content_stream=generate_content_stream)))


def test_gemini_het_luot_thi_sang_model_du_phong(monkeypatch):
    monkeypatch.setattr(tro_ly, "_het_luot_gemini", {})
    monkeypatch.setattr(tro_ly, "GEMINI_MODEL", "chinh")
    monkeypatch.setattr(tro_ly, "GEMINI_DU_PHONG", ["du_phong_1", "du_phong_2"])
    ghi = []
    monkeypatch.setattr(tro_ly, "_gemini", _gemini_theo_model({"chinh": _loi_gemini(429, "81853s"), "du_phong_1": _loi_gemini(503)}, ghi))
    ev = _chay(tro_ly.luong_ai("hỏi", [], DU_LIEU, "gemini"))
    assert ghi == ["chinh", "du_phong_1", "du_phong_2"]
    assert ev[0][1]["t"] == "Trả lời từ du_phong_2" and ev[-1][1]["model"] == "du_phong_2"
    # model chính bị bỏ qua tới khi hết thời gian chờ Google trả về; model quá tải (503) vẫn được thử lần sau
    assert tro_ly.cac_model_gemini() == ["du_phong_1", "du_phong_2"]
    assert tro_ly.cac_model_gemini(now=__import__("time").time() + 81900) == ["chinh", "du_phong_1", "du_phong_2"]


def test_gemini_loi_may_chu_504_sang_model_ke_con_loi_400_thi_dung(monkeypatch):
    monkeypatch.setattr(tro_ly, "_het_luot_gemini", {})
    monkeypatch.setattr(tro_ly, "GEMINI_MODEL", "chinh")
    monkeypatch.setattr(tro_ly, "GEMINI_DU_PHONG", ["phu"])
    ghi = []
    monkeypatch.setattr(tro_ly, "_gemini", _gemini_theo_model({"chinh": _loi_gemini(504)}, ghi))
    ev = _chay(tro_ly.luong_ai("hỏi", [], DU_LIEU, "gemini"))
    assert ghi == ["chinh", "phu"] and ev[-1][1]["model"] == "phu"
    ghi.clear()
    monkeypatch.setattr(tro_ly, "_gemini", _gemini_theo_model({"chinh": _loi_gemini(400)}, ghi))
    with pytest.raises(g_errors.APIError):
        _chay(tro_ly.luong_ai("hỏi", [], DU_LIEU, "gemini"))
    assert ghi == ["chinh"]                       # yêu cầu sai thì model khác cũng sai: không thử tiếp


def test_moi_model_het_luot_thi_khong_dung_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.delenv("TRO_LY_AI", raising=False)
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(tro_ly, "NHA_CUNG_CAP", "auto")
    monkeypatch.setattr(tro_ly, "GEMINI_MODEL", "chinh")
    monkeypatch.setattr(tro_ly, "GEMINI_DU_PHONG", ["phu"])
    monkeypatch.setattr(tro_ly, "_het_luot_gemini", {"chinh": 9e18, "phu": 9e18})
    assert tro_ly.nha_cung_cap() is None          # trả lời tự động ngay, không bắt người dùng chờ
