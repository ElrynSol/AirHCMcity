"""Kiểm thử xác thực (thay cho tests/test_api.py cũ). Chạy từ backend/: python -m pytest ../tests -q"""
import importlib
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))


def _nap(monkeypatch, khoa):
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    if khoa is None:
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    else:
        monkeypatch.setenv("JWT_SECRET_KEY", khoa)
    sys.modules.pop("auth", None)
    return importlib.import_module("auth")


def test_thieu_khoa_thi_dung(monkeypatch):
    with pytest.raises(RuntimeError):
        _nap(monkeypatch, None)


def test_khoa_ngan_bi_tu_choi(monkeypatch):
    with pytest.raises(RuntimeError):
        _nap(monkeypatch, "ngan")


def test_token_vong_doi_va_gia_mao(monkeypatch):
    a = _nap(monkeypatch, "k" * 40)
    t = a.create_access_token({"sub": "x@y.vn"})
    assert a.decode_access_token(t)["sub"] == "x@y.vn"
    assert a.decode_access_token(t + "x") is None
    # token ký bằng khóa công khai cũ phải bị từ chối
    from jose import jwt
    gia = jwt.encode({"sub": "admin"}, "fallback-key-neu-thieu-env-2026", algorithm="HS256")
    assert a.decode_access_token(gia) is None


def test_han_token_bang_han_cookie(monkeypatch):
    monkeypatch.setenv("COOKIE_MAX_AGE", "28800")
    a = _nap(monkeypatch, "k" * 40)
    assert a.ACCESS_TOKEN_EXPIRE_SECONDS == 28800
