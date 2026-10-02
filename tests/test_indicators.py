import numpy as np
import pandas as pd
import pytest

from lab import indicators as ind


def test_ema_matches_recursive_formula():
    s = pd.Series(np.arange(1, 31, dtype=float))
    e = ind.ema(s, 10)
    assert e.iloc[:9].isna().all()
    a = 2 / 11
    manual = s.iloc[0]
    for x in s.iloc[1:]:
        manual = a * x + (1 - a) * manual
    assert e.iloc[-1] == pytest.approx(manual)


def test_rsi_bounds_and_extremes():
    up = pd.Series(np.arange(1, 50, dtype=float))
    assert ind.rsi(up).iloc[-1] == pytest.approx(100.0)
    down = pd.Series(np.arange(50, 1, -1, dtype=float))
    assert ind.rsi(down).iloc[-1] == pytest.approx(0.0)
    rng = np.random.default_rng(0)
    r = ind.rsi(pd.Series(100 + rng.normal(0, 1, 500).cumsum())).dropna()
    assert ((r >= 0) & (r <= 100)).all()


def test_atr_constant_range(ohlcv):
    df = ohlcv([100.0] * 60, spread=0.01)
    a = ind.atr(df).iloc[-1]
    assert a == pytest.approx(2.0, rel=1e-6)  # high-low = 101-99


def test_adx_high_in_strong_trend(ohlcv):
    df = ohlcv(100 * 1.01 ** np.arange(200))
    assert ind.adx(df).iloc[-1] > 40


def test_indicators_are_causal(ohlcv):
    rng = np.random.default_rng(1)
    closes = 100 + rng.normal(0, 1, 400).cumsum()
    a = ind.add_indicators(ohlcv(closes))
    closes2 = closes.copy()
    closes2[300:] *= 1.5  # change the future
    b = ind.add_indicators(ohlcv(closes2))
    cols = ["ema20", "ema50", "ema200", "rsi", "atr", "adx", "vol_avg20", "high20_prev"]
    pd.testing.assert_frame_equal(a[cols].iloc[:300], b[cols].iloc[:300])
