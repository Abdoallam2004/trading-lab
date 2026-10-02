"""Point-in-time signal series. Every value at day t is computed from data <= t only
(expanding ATH, expanding std, expanding monthly-refit regressions, completed weeks only).
tests/test_lab2_lookahead.py checks this by truncating / extending the data by one bar.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .data import days_since_genesis


def sunday_closes(price: pd.Series) -> pd.Series:
    """Closes of completed weeks (the Sunday daily bar closes the Binance week)."""
    return price[price.index.dayofweek == 6]


def weekly_sma_asof(price: pd.Series, weeks: int) -> pd.Series:
    """SMA of the last `weeks` completed weekly closes, as known on each day."""
    w = sunday_closes(price).rolling(weeks, min_periods=weeks).mean()
    return w.reindex(price.index, method="ffill")


def regime_up(price: pd.Series, kind: str) -> pd.Series:
    """S1: close above its SMA. kind: '200d' (daily SMA) | '50w' | '20w' (weekly SMA)."""
    if kind.endswith("d"):
        sma = price.rolling(int(kind[:-1]), min_periods=int(kind[:-1])).mean()
    else:
        sma = weekly_sma_asof(price, int(kind[:-1]))
    return (price > sma).where(sma.notna())


def ratio_to_200w(price: pd.Series) -> pd.Series:
    """S2: price / 200-week SMA (completed weeks)."""
    return price / weekly_sma_asof(price, 200)


def drawdown_from_ath(price: pd.Series) -> pd.Series:
    """S3: fraction below the expanding all-time high (0.4 = 40% below ATH)."""
    return 1.0 - price / price.cummax()


def logreg_z(price: pd.Series, min_years: float = 4.0) -> pd.Series:
    """S4: residual z-score of log10(price) ~ a + b*log10(days since genesis).

    Refit on the first day of every month using only data strictly before that day
    (expanding window, at least `min_years` of data); the month's days use that fit.
    """
    lp = np.log10(price.to_numpy(float))
    ld = np.log10(days_since_genesis(price.index))
    z = pd.Series(np.nan, index=price.index)
    months = price.index.tz_localize(None).to_period("M").unique()
    first = price.index[0]
    for m in months:
        m_start = m.to_timestamp().tz_localize("UTC")
        if (m_start - first).days < min_years * 365.25:
            continue
        fit = price.index < m_start
        if fit.sum() < 100:
            continue
        b, a = np.polyfit(ld[fit], lp[fit], 1)
        resid_sd = np.std(lp[fit] - (a + b * ld[fit]), ddof=1)
        cur = (price.index >= m_start) & (price.index < (m + 1).to_timestamp().tz_localize("UTC"))
        z[cur] = (lp[cur] - (a + b * ld[cur])) / resid_sd
    return z


def mvrv_z(mvrv: pd.DataFrame, min_obs: int = 365) -> pd.Series:
    """S5: (market cap - realized cap) / expanding std of market cap."""
    sd = mvrv["mc"].expanding(min_periods=min_obs).std()
    return ((mvrv["mc"] - mvrv["rc"]) / sd).rename("mvrv_z")


def momentum(close: pd.Series, days: int = 28) -> pd.Series:
    """S6: trailing `days` return (4 weeks)."""
    return close / close.shift(days) - 1


@dataclass(frozen=True)
class Pivot:
    kind: str          # "H" swing high | "L" swing low
    price: float
    pivot_time: pd.Timestamp
    confirm_time: pd.Timestamp  # first bar on which the pivot is known


def zigzag(high: pd.Series, low: pd.Series, threshold: float) -> list[Pivot]:
    """Point-in-time ZigZag on daily highs/lows.

    A swing high H is confirmed on the first bar whose low is >= `threshold` below H;
    a swing low L on the first bar whose high is >= `threshold` above L.
    """
    hi, lo, idx = high.to_numpy(float), low.to_numpy(float), high.index
    pivots: list[Pivot] = []
    if len(hi) == 0:
        return pivots
    mode = None  # unknown until the first move of `threshold`
    ext_hi, ext_hi_i, ext_lo, ext_lo_i = hi[0], 0, lo[0], 0
    for i in range(1, len(hi)):
        if mode in (None, "up"):
            if hi[i] > ext_hi:
                ext_hi, ext_hi_i = hi[i], i
            if lo[i] <= ext_hi * (1 - threshold) and (mode == "up" or ext_hi_i < i):
                pivots.append(Pivot("H", ext_hi, idx[ext_hi_i], idx[i]))
                mode, ext_lo, ext_lo_i = "down", lo[i], i
                continue
        if mode in (None, "down"):
            if lo[i] < ext_lo:
                ext_lo, ext_lo_i = lo[i], i
            if hi[i] >= ext_lo * (1 + threshold) and (mode == "down" or ext_lo_i < i):
                pivots.append(Pivot("L", ext_lo, idx[ext_lo_i], idx[i]))
                mode, ext_hi, ext_hi_i = "up", hi[i], i
    return pivots


def fib_setups(pivots: list[Pivot], entry_ret: float = 0.618, stop_ret: float = 0.786,
               stop_buffer: float = 0.005) -> pd.DataFrame:
    """S7: one pullback setup per confirmed up-swing (L -> H).

    entry = H - 61.8% of the swing, stop just below the 78.6% retracement, target = H.
    The setup is live from the bar after H is confirmed until the next pivot is confirmed.
    """
    rows = []
    for k in range(1, len(pivots)):
        p, q = pivots[k - 1], pivots[k]
        if not (p.kind == "L" and q.kind == "H"):
            continue
        swing = q.price - p.price
        expires = pivots[k + 1].confirm_time if k + 1 < len(pivots) else pd.Timestamp.max.tz_localize("UTC")
        rows.append({"live_from": q.confirm_time, "expires": expires, "swing_low": p.price, "swing_high": q.price,
                     "entry": q.price - entry_ret * swing,
                     "stop": (q.price - stop_ret * swing) * (1 - stop_buffer), "target": q.price})
    return pd.DataFrame(rows, columns=["live_from", "expires", "swing_low", "swing_high", "entry", "stop", "target"])
