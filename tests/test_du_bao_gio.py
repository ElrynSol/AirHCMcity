"""Kiểm thử nhanh cho dự báo theo giờ (chạy từ thư mục backend: python -m pytest ../tests/test_du_bao_gio.py -q)."""
import numpy as np
import pandas as pd
from services import du_bao_gio as d


def _df(n=24 * 60):
    t = pd.date_range("2024-01-01", periods=n, freq="h")
    rng = np.random.default_rng(0)
    p = 20 + 5 * np.sin(np.arange(n) / 7) + rng.normal(0, 1, n)
    return pd.DataFrame({"time": t, "pm2_5": p, "pm10": p * 1.2, "temperature_2m": 28.0, "relative_humidity_2m": 70.0,
                         "wind_speed_10m": 3.0, "precipitation": 0.0, "surface_pressure": 1010.0})


def test_dac_trung_khong_nhin_tuong_lai():
    df = _df()
    day, cat = d.tao_dac_trung(df), d.tao_dac_trung(df.iloc[:800])
    cot = [c for c in d.DAC_TRUNG if c not in ("buoc", "dich_sin", "dich_cos")]
    assert np.allclose(day.iloc[799][cot].astype(float), cat.iloc[799][cot].astype(float), equal_nan=True)


def test_tap_huan_luyen_nhan_la_tuong_lai():
    df = _df()
    X, yd, p0, yt, tt, hh = d.tao_tap_huan_luyen(df, buoc=[3])
    i = 100
    t = pd.Timestamp(tt[i])
    that = df.set_index("time")["pm2_5"]
    assert abs(yt[i] - that[t + pd.Timedelta(hours=3)]) < 1e-9
    assert abs(p0[i] - that[t]) < 1e-9


def test_khung_gio_tot_xau():
    ds = [{"gio": f"2026-10-16T{h:02d}:00", "pm25": v} for h, v in enumerate([30] * 5 + [10] * 3 + [30] * 8 + [60] * 3 + [30] * 5)]
    tot, xau = d.khung_gio_tot_xau(ds, 3)
    assert tot["pm25_tb"] == 10 and xau["pm25_tb"] == 60
