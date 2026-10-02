"""Market regime: BTC daily close above / below its 200-day simple moving average.

The regime of day D is only known after D closes, so it is stamped at D+1 00:00 UTC
and looked up "as of" each trade's entry time (no look-ahead).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

BULL, BEAR, UNKNOWN = "BTC>200D", "BTC<200D", "warmup"


def btc_regime(btc_daily: pd.DataFrame, ma: int = 200) -> pd.Series:
    close = btc_daily["close"]
    sma = close.rolling(ma, min_periods=ma).mean()
    lab = pd.Series(np.where(sma.isna(), UNKNOWN, np.where(close > sma, BULL, BEAR)), index=close.index)
    lab.index = lab.index + pd.Timedelta(days=1)  # known at the next day's open
    return lab


def regime_at(regime: pd.Series, times) -> np.ndarray:
    times = pd.DatetimeIndex(times)
    if len(regime) == 0:
        return np.full(len(times), UNKNOWN, dtype=object)
    pos = regime.index.as_unit("ns").searchsorted(times.as_unit("ns"), side="right") - 1
    vals = regime.to_numpy(dtype=object)
    return np.where(pos >= 0, vals[np.clip(pos, 0, None)], UNKNOWN)


def current_regime(btc_daily: pd.DataFrame, ma: int = 200) -> str:
    reg = btc_regime(btc_daily, ma)
    return str(reg.iloc[-1]) if len(reg) else UNKNOWN
