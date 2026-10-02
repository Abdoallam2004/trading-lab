"""Lab 3 data: Binance spot klines for BTCUSDT / ETHUSDT on 1m..1d, with a LOCKED HOLDOUT.

Every loader cuts the data at DEV_END (2025-09-30 23:59:59 UTC) unless `holdout=True` is
passed explicitly. Only scripts/run_lab3_holdout.py passes it, once, after all choices are
frozen in reports/lab3_frozen.json.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import pandas as pd

from lab import data as lab1
from lab.config import DATA_DIR

LAB3_DIR = DATA_DIR / "lab3"
ASSETS = ("BTCUSDT", "ETHUSDT")
TIMEFRAMES = ("1m", "5m", "15m", "1h", "4h", "1d")
DEV_END = pd.Timestamp("2025-09-30 23:59:59", tz="UTC")
HOLDOUT_START = pd.Timestamp("2025-10-01", tz="UTC")
HOLDOUT_END = pd.Timestamp("2026-09-30 23:59:59", tz="UTC")
DOWNLOAD_START = {"1m": "2020-12-01", "5m": "2019-01-01", "15m": "2019-01-01", "1h": "2019-01-01",
                  "4h": "2019-01-01", "1d": "2017-08-01"}
TF_DELTA = {"1m": pd.Timedelta(minutes=1), "5m": pd.Timedelta(minutes=5), "15m": pd.Timedelta(minutes=15),
            "1h": pd.Timedelta(hours=1), "4h": pd.Timedelta(hours=4), "1d": pd.Timedelta(days=1)}


class HoldoutLocked(RuntimeError):
    pass


def download(today: date = date(2026, 10, 2), log=print) -> None:
    dl = lab1.Downloader()
    jobs = [(s, tf) for s in ASSETS for tf in TIMEFRAMES]

    def one(job):
        s, tf = job
        df = lab1.update_symbol(s, tf, dl, start=DOWNLOAD_START[tf], today=today, data_dir=LAB3_DIR, workers=8)
        return s, tf, len(df), df.index[0] if len(df) else None, df.index[-1] if len(df) else None

    with ThreadPoolExecutor(max_workers=4) as ex:
        for s, tf, n, a, b in ex.map(one, jobs):
            log(f"  {s} {tf}: {n} bars {a} .. {b}")


def load_bars(symbol: str, tf: str, holdout: bool = False, data_dir: Path = LAB3_DIR) -> pd.DataFrame:
    """OHLCV bars. Without holdout=True nothing after 2025-09-30 is returned."""
    df = lab1.load(symbol, tf, data_dir)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    if not holdout:
        df = df[df.index <= DEV_END]
    return df


def assert_no_holdout(*frames) -> None:
    """Guard used by every development-time analysis."""
    for f in frames:
        if len(f) and f.index[-1] > DEV_END:
            raise HoldoutLocked("holdout data reached a development-time analysis")
