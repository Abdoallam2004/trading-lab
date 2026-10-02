import numpy as np
import pandas as pd
import pytest

from lab.engine import ExitConfig
from lab.indicators import add_indicators
from lab.strategies import (SPEC_PARAMS, StrategyConfig, config_grid, make_setup, signal_mask,
                            stop_levels)


def frame(n=300, **cols):
    idx = pd.date_range("2021-01-01", periods=n, freq="1D", tz="UTC")
    base = {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000.0,
            "ema20": 100.0, "ema50": 100.0, "ema200": 90.0, "rsi": 50.0, "atr": 2.0, "adx": 25.0,
            "vol_avg20": 1000.0, "high20_prev": 105.0}
    base.update(cols)
    return pd.DataFrame({k: (v if np.ndim(v) else np.full(n, float(v))) for k, v in base.items()}, index=idx)


def test_pullback_rules():
    p = SPEC_PARAMS["PULLBACK"]
    assert signal_mask(frame(), "PULLBACK", p).all()
    assert not signal_mask(frame(ema200=110.0), "PULLBACK", p).any()     # not an uptrend
    assert not signal_mask(frame(rsi=65.0), "PULLBACK", p).any()         # RSI out of band
    assert not signal_mask(frame(close=104.0, ema20=100.0, ema50=100.0), "PULLBACK", p).any()  # 2 ATR away
    assert signal_mask(frame(close=101.9, ema20=104, ema50=100.0), "PULLBACK", p).all()        # near EMA50


def test_breakout_rules():
    p = SPEC_PARAMS["BREAKOUT"]
    assert signal_mask(frame(close=106.0, volume=1500.0), "BREAKOUT", p).all()
    assert not signal_mask(frame(close=106.0, volume=1400.0), "BREAKOUT", p).any()  # weak volume
    assert not signal_mask(frame(close=104.0, volume=2000.0), "BREAKOUT", p).any()  # no breakout


def test_base_rules():
    n = 10
    close = np.full(n, 95.0)
    close[5] = 101.0  # reclaim above EMA50=100 on bar 5
    adx = np.arange(10.0, 10.0 + 3 * n, 3)  # rising
    d = frame(n, close=close, ema50=100.0, ema200=110.0, adx=adx)
    sig = signal_mask(d, "BASE", SPEC_PARAMS["BASE"])
    assert list(np.flatnonzero(sig)) == [5]
    d2 = frame(n, close=close, ema50=100.0, ema200=90.0, adx=adx)  # already above EMA200 -> not a base
    assert not signal_mask(d2, "BASE", SPEC_PARAMS["BASE"]).any()
    d3 = frame(n, close=close, ema50=100.0, ema200=110.0, adx=adx[::-1].copy())  # falling ADX
    assert not signal_mask(d3, "BASE", SPEC_PARAMS["BASE"]).any()


def test_stop_is_swing_low_minus_half_atr():
    low = np.arange(100.0, 120.0)
    d = frame(20, low=low, atr=2.0)
    s = stop_levels(d, 10)
    assert s.iloc[-1] == pytest.approx(110.0 - 1.0)
    assert s.iloc[:9].isna().all()


def test_signals_need_warmed_up_indicators(ohlcv):
    d = add_indicators(ohlcv(np.linspace(100, 200, 150)))  # < 200 bars -> no EMA200
    for name in SPEC_PARAMS:
        assert not signal_mask(d, name, SPEC_PARAMS[name]).any()


def test_signals_do_not_look_ahead(ohlcv):
    rng = np.random.default_rng(3)
    closes = 100 * np.exp(rng.normal(0.001, 0.03, 600).cumsum())
    vol = rng.uniform(500, 3000, 600)
    a = add_indicators(ohlcv(closes, volume=vol))
    c2 = closes.copy(); c2[450:] *= 0.5
    b = add_indicators(ohlcv(c2, volume=vol))
    for name in SPEC_PARAMS:
        sa = signal_mask(a, name, SPEC_PARAMS[name]).iloc[:450]
        sb = signal_mask(b, name, SPEC_PARAMS[name]).iloc[:450]
        pd.testing.assert_series_equal(sa, sb)


def test_config_roundtrip_and_grid():
    grid = config_grid("PULLBACK")
    assert len(grid) == len(set(grid)) == 2 * 4 * 4
    cfg = StrategyConfig.make("BREAKOUT", "4h", SPEC_PARAMS["BREAKOUT"], ExitConfig("trail", 3.0))
    assert StrategyConfig.from_dict(cfg.to_dict()) == cfg


def test_make_setup_produces_valid_stops(ohlcv):
    rng = np.random.default_rng(4)
    closes = 100 * np.exp(rng.normal(0.002, 0.03, 700).cumsum())
    d = add_indicators(ohlcv(closes, volume=rng.uniform(500, 3000, 700)))
    cfg = StrategyConfig.make("PULLBACK", "1d", SPEC_PARAMS["PULLBACK"])
    st = make_setup(d, cfg)
    assert len(st.signal_idx) > 0
    assert (st.stops < d["close"].to_numpy()[st.signal_idx]).all()
