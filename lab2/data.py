"""Lab 2 data: full-history Binance daily klines + free CoinMetrics BTC history.

* Binance spot daily klines: Lab 1's cache (2019-10 →) is extended back to the start of
  the archive (2017-08) in data/early/, and the two are merged per symbol.
* CoinMetrics community CSV (github.com/coinmetrics/data, csv/btc.csv): PriceUSD from 2010
  is used ONLY for long-lookback signals (200-week SMA, log regression, ATH before 2017-08).
  Realized cap is not in the free file, but CapMVRVCur (= market cap / realized cap) and
  CapMrktCurUSD are, so realized cap = CapMrktCurUSD / CapMVRVCur exactly.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from lab import data as lab1
from lab.config import DATA_DIR

EARLY_DIR = DATA_DIR / "early"
EXTERNAL_DIR = DATA_DIR / "external"
COINMETRICS_URL = "https://raw.githubusercontent.com/coinmetrics/data/master/csv/btc.csv"
COINMETRICS_FILE = EXTERNAL_DIR / "coinmetrics_btc.csv"
EARLY_START = "2017-08-01"
EARLY_END = date(2019, 10, 1)  # Lab 1's cache starts here
GENESIS = pd.Timestamp("2009-01-03", tz="UTC")


def download_early(symbols: list[str], dl: lab1.Downloader | None = None, workers: int = 8, log=print) -> dict:
    """Fetch 2017-08 → 2019-09 daily klines into data/early (only files that exist)."""
    from concurrent.futures import ThreadPoolExecutor

    dl = dl or lab1.Downloader()

    def one(sym):
        try:
            return sym, len(lab1.update_symbol(sym, "1d", dl, start=EARLY_START, today=EARLY_END,
                                               data_dir=EARLY_DIR, workers=4))
        except Exception as e:  # keep going
            log(f"  {sym}: ERROR {e}")
            return sym, -1

    out = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, (sym, n) in enumerate(ex.map(one, symbols), 1):
            out[sym] = n
            if i % 50 == 0 or i == len(symbols):
                log(f"  early 1d [{i}/{len(symbols)}]")
    return out


def download_coinmetrics(path: Path = COINMETRICS_FILE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(COINMETRICS_URL, timeout=120)
    r.raise_for_status()
    path.write_bytes(r.content)
    return path


def load_full(symbol: str, data_dir: Path = DATA_DIR, early_dir: Path = EARLY_DIR) -> pd.DataFrame:
    """Merged daily klines (early archive + Lab 1 cache)."""
    frames = []
    for d in (early_dir, data_dir):
        try:
            frames.append(lab1.load(symbol, "1d", d))
        except FileNotFoundError:
            pass
    if not frames:
        raise FileNotFoundError(symbol)
    return lab1.merge_frames(frames)


def load_full_segments(symbol: str, data_dir: Path = DATA_DIR, early_dir: Path = EARLY_DIR) -> dict[str, pd.DataFrame]:
    """Merged daily klines split at token redenominations (Lab 1 rule)."""
    segs = lab1.split_redenominations(load_full(symbol, data_dir, early_dir), "1d")
    return {lab1.segment_name(symbol, sg, k == len(segs) - 1): sg for k, sg in enumerate(segs)}


def load_coinmetrics(path: Path = COINMETRICS_FILE) -> pd.DataFrame:
    cm = pd.read_csv(path, usecols=["time", "PriceUSD", "CapMrktCurUSD", "CapMVRVCur", "SplyCur"])
    cm["time"] = pd.to_datetime(cm["time"], utc=True)
    cm = cm.set_index("time").sort_index().dropna(subset=["PriceUSD"])
    cm["CapRealUSD"] = cm["CapMrktCurUSD"] / cm["CapMVRVCur"]
    return cm


def signal_price(btc: pd.DataFrame, cm: pd.DataFrame) -> pd.Series:
    """BTC daily close for SIGNALS: CoinMetrics PriceUSD before Binance's first bar, Binance after."""
    first = btc.index[0]
    early = cm.loc[cm.index < first, "PriceUSD"]
    s = pd.concat([early, btc["close"]])
    return s[~s.index.duplicated(keep="last")].sort_index().rename("price")


def mvrv_inputs(cm: pd.DataFrame, btc: pd.DataFrame) -> pd.DataFrame:
    """Daily market cap and realized cap, known one day later (publication lag).

    After the CoinMetrics file ends, market cap = Binance close x last known supply and
    realized cap is carried forward (flagged in the `stale` column).
    """
    idx = btc.index.union(cm.index)
    out = pd.DataFrame(index=idx)
    out["mc"] = cm["CapMrktCurUSD"].reindex(idx)
    out["rc"] = cm["CapRealUSD"].reindex(idx)
    last_cm = cm["CapMrktCurUSD"].last_valid_index()
    supply = cm["SplyCur"].reindex(idx).ffill()
    after = out.index > last_cm
    out.loc[after, "mc"] = btc["close"].reindex(idx)[after] * supply[after]
    out["rc"] = out["rc"].ffill()
    out["stale"] = after
    out = out.shift(1)  # value for day t is only published after t closes
    return out.dropna(subset=["mc", "rc"])


def days_since_genesis(idx: pd.DatetimeIndex) -> np.ndarray:
    return ((idx - GENESIS) / pd.Timedelta(days=1)).to_numpy(float)
