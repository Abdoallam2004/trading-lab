"""Bars + causal indicators for Part B (value at bar i uses bars <= i only)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from lab.indicators import atr as wilder_atr
from lab.indicators import ema, rsi

from .data import TF_DELTA, assert_no_holdout, load_bars
from .engine import Bars


def pivots(values: np.ndarray, k: int, kind: str) -> np.ndarray:
    """Fractal pivots, reported at their CONFIRMATION bar.

    out[t] = True when bar t-k is a pivot high (low): strictly above (below) the k bars before
    it and the k bars after it. Uses values[t-2k .. t] only, so out[t] is known at t's close.
    """
    s = pd.Series(values)
    cand = s.shift(k)
    if kind == "high":
        left = s.shift(k + 1).rolling(k, min_periods=k).max()
        right = s.rolling(k, min_periods=k).max()
        out = (cand > left) & (cand > right)
    else:
        left = s.shift(k + 1).rolling(k, min_periods=k).min()
        right = s.rolling(k, min_periods=k).min()
        out = (cand < left) & (cand < right)
    return out.fillna(False).to_numpy(bool)


class Market:
    """Lazy cache of bars and indicators per (asset, timeframe)."""

    def __init__(self, holdout: bool = False, frames: dict | None = None):
        """`frames` = {(asset, tf): ohlcv DataFrame} replaces the files (used by the tests)."""
        self.holdout = holdout
        self.frames = frames
        self._df: dict = {}
        self._bars: dict = {}
        self._btc_up_daily = None

    def df(self, asset: str, tf: str) -> pd.DataFrame:
        key = (asset, tf)
        if key not in self._df:
            d = self.frames[key] if self.frames is not None else load_bars(asset, tf, holdout=self.holdout)
            if not self.holdout:
                assert_no_holdout(d)
            d = d.copy()
            d.index = d.index.as_unit("ns")
            d["ema200"] = ema(d["close"], 200)
            d["atr"] = wilder_atr(d, 14)
            d["rsi"] = rsi(d["close"], 14)
            d["body"] = (d["close"] - d["open"]).abs()
            d["green"] = d["close"] > d["open"]
            d["btc_up"] = self.btc_up_at_close(d.index, tf)
            self._df[key] = d
        return self._df[key]

    def bars(self, asset: str, tf: str) -> Bars:
        key = (asset, tf)
        if key not in self._bars:
            self._bars[key] = Bars(self.df(asset, tf))
        return self._bars[key]

    def btc_up_at_close(self, index: pd.DatetimeIndex, tf: str) -> np.ndarray:
        """BTC daily close > 200-day SMA, as known when each bar closes (daily flag of day D is
        known from D+1 00:00)."""
        if self._btc_up_daily is None:
            d = (self.frames[("BTCUSDT", "1d")] if self.frames is not None
                 else load_bars("BTCUSDT", "1d", holdout=self.holdout))
            sma = d["close"].rolling(200, min_periods=200).mean()
            flag = (d["close"] > sma).where(sma.notna(), False)
            known = pd.Series(flag.to_numpy(bool), index=(d.index + pd.Timedelta(days=1)).as_unit("ns"))
            self._btc_up_daily = known
        closes = (index + TF_DELTA[tf]).as_unit("ns")
        pos = self._btc_up_daily.index.searchsorted(closes, side="right") - 1
        vals = self._btc_up_daily.to_numpy(bool)
        return np.where(pos >= 0, vals[np.clip(pos, 0, None)], False)
