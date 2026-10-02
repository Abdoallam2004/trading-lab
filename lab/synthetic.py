"""Synthetic market data for tests and offline smoke runs.

Prices are random (regime-switching geometric Brownian motion). Results computed on
this data say NOTHING about real markets; reports built from it are watermarked.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import data as data_mod

SYNTHETIC_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "LINKUSDT", "AVAXUSDT", "DOTUSDT"]


def synth_4h(symbol: str, start: str = "2020-01-01", end: str = "2026-09-30", seed: int | None = None) -> pd.DataFrame:
    rng = np.random.default_rng(seed if seed is not None else abs(hash(symbol)) % 2**32)
    idx = pd.date_range(start, end, freq="4h", tz="UTC", inclusive="left", name="open_time")
    n = len(idx)
    # regimes lasting ~3-9 months with drift up / down / flat
    drift = np.empty(n)
    i = 0
    while i < n:
        length = int(rng.integers(540, 1620))
        drift[i:i + length] = rng.choice([0.0012, -0.0009, 0.0], p=[0.45, 0.3, 0.25])
        i += length
    vol = 0.018 * np.exp(rng.normal(0, 0.25, n))
    rets = drift + vol * rng.standard_normal(n)
    close = 100 * np.exp(np.cumsum(rets)) * (1 + 50 * (symbol == "BTCUSDT"))
    open_ = np.r_[close[0], close[:-1]]
    wick = np.abs(rng.normal(0, 0.006, (2, n)))
    high = np.maximum(open_, close) * (1 + wick[0])
    low = np.minimum(open_, close) * (1 - wick[1])
    volume = rng.lognormal(10, 0.4, n) * (1 + 4 * (np.abs(rets) > 2.2 * vol))
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume,
                         "quote_volume": volume * close, "trades": rng.integers(100, 5000, n).astype(float)},
                        index=idx)


def to_daily(df4h: pd.DataFrame) -> pd.DataFrame:
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum",
           "quote_volume": "sum", "trades": "sum"}
    d = df4h.resample("1D").agg(agg).dropna()
    d.index.name = "open_time"
    return d


def write_synthetic(data_dir: Path, symbols=SYNTHETIC_SYMBOLS, start="2020-01-01", end="2026-09-30") -> list[str]:
    vols = {}
    for k, s in enumerate(symbols):
        h4 = synth_4h(s, start, end, seed=1000 + k)
        d1 = to_daily(h4)
        data_mod.save(h4, s, "4h", data_dir)
        data_mod.save(d1, s, "1d", data_dir)
        vols[s] = float(d1["quote_volume"].iloc[-30:].sum())
    data_mod.save_universe(list(symbols), pd.Series(vols), data_dir, source="synthetic")
    return list(symbols)
