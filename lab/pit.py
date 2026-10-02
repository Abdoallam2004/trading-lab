"""Point-in-time universe: which coins were the top N *at a past date*, using only data known then.

At date D a coin is a candidate if
  * it passes the exclusion rules (stablecoins, leveraged, meme, tokenized stocks ...),
  * it was already trading: at least `min_days` daily bars in the lookback window before D,
  * it was still trading: its last bar is no older than `max_stale_days` before D.
Candidates are ranked by USDT quote volume over [D - lookback_months, D).

This removes survivorship bias: coins that later collapsed or were delisted (LUNA, FTT ...)
are in the universe for the periods when they were big, and coins listed later are not.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import data as data_mod
from .config import DATA_DIR, TOP_N
from .universe import exclusion_reason


def rank_point_in_time(volumes: dict[str, pd.Series], when, top_n: int = TOP_N, lookback_months: int = 3,
                       min_days: int = 20, max_stale_days: int = 7) -> list[str]:
    """volumes[symbol] = daily quote_volume series (UTC DatetimeIndex)."""
    when = pd.Timestamp(when)
    when = when.tz_localize("UTC") if when.tz is None else when.tz_convert("UTC")
    lo = when - pd.DateOffset(months=lookback_months)
    scores = {}
    for sym, v in volumes.items():
        if exclusion_reason(sym) is not None or len(v) == 0:
            continue
        if v.index[0] >= when or v.index[-1] < when - pd.Timedelta(days=max_stale_days):
            continue  # not listed yet / already delisted
        w = v[(v.index >= lo) & (v.index < when)]
        if len(w) < min_days:
            continue
        scores[sym] = float(w.sum())
    ranked = sorted(scores, key=lambda s: (-scores[s], s))
    return ranked[:top_n]


class PointInTimeUniverse:
    """Callable date -> top-N list, memoised, backed by the daily cache of every candidate."""

    def __init__(self, volumes: dict[str, pd.Series], top_n: int = TOP_N, lookback_months: int = 3):
        self.volumes = volumes
        self.top_n = top_n
        self.lookback_months = lookback_months
        self._memo: dict = {}

    @classmethod
    def from_cache(cls, symbols, data_dir: Path = DATA_DIR, **kw) -> "PointInTimeUniverse":
        vols = {}
        for s in symbols:
            try:
                vols[s] = data_mod.load(s, "1d", data_dir)["quote_volume"]
            except FileNotFoundError:
                pass
        return cls(vols, **kw)

    def __call__(self, when) -> list[str]:
        key = pd.Timestamp(when)
        if key not in self._memo:
            self._memo[key] = rank_point_in_time(self.volumes, key, self.top_n, self.lookback_months)
        return self._memo[key]

    def monthly(self, start, end) -> dict[str, list[str]]:
        dates = pd.date_range(pd.Timestamp(start).normalize(), end, freq="MS", tz="UTC")
        return {f"{d:%Y-%m-%d}": self(d) for d in dates}
