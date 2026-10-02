"""Causal technical indicators (value at bar t uses only bars <= t)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(s: pd.Series, span: int) -> pd.Series:
    out = s.ewm(span=span, adjust=False, min_periods=span).mean()
    return out


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def wilder(s: pd.Series, n: int) -> pd.Series:
    """Wilder smoothing (RMA), alpha = 1/n."""
    return s.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    gain = wilder(d.clip(lower=0), n)
    loss = wilder(-d.clip(upper=0), n)
    rs = gain / loss
    out = 100 - 100 / (1 + rs)
    out = out.where(loss != 0, 100.0)
    return out.where(gain.notna())


def true_range(df: pd.DataFrame) -> pd.Series:
    prev = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1)
    return tr.max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return wilder(true_range(df), n)


def adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    tr = wilder(true_range(df), n)
    plus_di = 100 * wilder(plus_dm, n) / tr
    minus_di = 100 * wilder(minus_dm, n) / tr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return wilder(dx, n)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with every indicator the strategies need."""
    out = df.copy()
    c = out["close"]
    out["ema20"] = ema(c, 20)
    out["ema50"] = ema(c, 50)
    out["ema200"] = ema(c, 200)
    out["rsi"] = rsi(c, 14)
    out["atr"] = atr(out, 14)
    out["adx"] = adx(out, 14)
    out["vol_avg20"] = sma(out["volume"], 20).shift(1)  # average of the 20 bars before this one
    out["high20_prev"] = out["high"].rolling(20, min_periods=20).max().shift(1)
    return out
