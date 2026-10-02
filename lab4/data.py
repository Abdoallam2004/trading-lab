"""Lab 4 data: everything free and reachable, cached as parquet in data/lab4/.

Point-in-time conventions (see reports/lab4_data_inventory.md):
  * spot / premium-index klines: a bar is known at its close (open_time + interval);
  * funding rate: known at its calc_time (the settlement timestamp);
  * futures metrics (open interest, long/short ratios, taker ratio): known at create_time
    (5-minute snapshots, the same values the public API serves at that moment);
  * VIX daily close (CBOE via datasets/finance-vix): a US-session value, known from 21:00 UTC
    of its date -> aligned to the next 00:00 UTC (conservative "release" timestamp);
  * PAXG/USDT (gold proxy) and EUR/USDT (dollar proxy, inverted): Binance daily klines.
"""
from __future__ import annotations

import io
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from lab import data as lab1
from lab.config import DATA_DIR

LAB4_DIR = DATA_DIR / "lab4"
ASSETS = ("BTCUSDT", "ETHUSDT")
VIX_URL = "https://raw.githubusercontent.com/datasets/finance-vix/main/data/vix-daily.csv"
US10Y_MONTHLY_URL = "https://raw.githubusercontent.com/datasets/bond-yields-us-10y/main/data/monthly.csv"
KLINE_ALL = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trades",
             "taker_buy_base", "taker_buy_quote", "ignore"]


def _ts(x: pd.Series) -> pd.DatetimeIndex:
    x = pd.to_numeric(x).astype("int64")
    x = x.where(x < 10**14, x // 1000)  # microseconds -> ms
    return pd.DatetimeIndex(pd.to_datetime(x, unit="ms", utc=True)).as_unit("ns")


def _read_zip_csv(content: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        frames = []
        for name in zf.namelist():
            if not name.endswith(".csv"):
                continue
            raw = zf.read(name).decode()
            first = raw.split("\n", 1)[0].split(",")[0].strip()
            header = None if first.lstrip("-").isdigit() else 0
            frames.append(pd.read_csv(io.StringIO(raw), header=header))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def parse_klines(df: pd.DataFrame) -> pd.DataFrame:
    df = df.iloc[:, :12].copy()
    df.columns = KLINE_ALL
    out = df[["open", "high", "low", "close", "volume", "quote_volume", "taker_buy_quote"]].astype(float)
    out.index = _ts(df["open_time"]).rename("open_time")
    return out


def parse_funding(df: pd.DataFrame) -> pd.DataFrame:
    cols = {c.lower(): c for c in df.columns}
    t = df[cols.get("calc_time", df.columns[0])]
    rate = df[cols.get("last_funding_rate", df.columns[-1])]
    out = pd.DataFrame({"funding": pd.to_numeric(rate, errors="coerce").to_numpy()}, index=_ts(t).rename("time"))
    return out.dropna()


def parse_metrics(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    t = pd.to_datetime(df["create_time"], utc=True).dt.tz_convert("UTC")
    keep = ["sum_open_interest", "sum_open_interest_value", "count_toptrader_long_short_ratio",
            "sum_toptrader_long_short_ratio", "count_long_short_ratio", "sum_taker_long_short_vol_ratio"]
    out = df[[c for c in keep if c in df.columns]].apply(pd.to_numeric, errors="coerce")
    out.index = pd.DatetimeIndex(t).as_unit("ns").rename("time")
    return out


class Fetcher:
    def __init__(self, workers: int = 16):
        self.dl = lab1.Downloader()
        self.workers = workers

    def archive(self, prefix: str, parse) -> pd.DataFrame:
        """Every .zip under an archive prefix, parsed and concatenated (sorted, de-duplicated)."""
        keys = [k for k in self.dl.list_keys(prefix) if k.endswith(".zip")]

        def one(k):
            content = self.dl.get(f"{lab1.BASE_URL}/{k}")
            return parse(_read_zip_csv(content)) if content else None

        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            parts = [p for p in ex.map(one, keys) if p is not None and len(p)]
        if not parts:
            return pd.DataFrame()
        df = pd.concat(parts).sort_index()
        return df[~df.index.duplicated(keep="last")]


def path(name: str) -> Path:
    return LAB4_DIR / f"{name}.parquet"


def save(df: pd.DataFrame, name: str) -> None:
    LAB4_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path(name))


def load(name: str) -> pd.DataFrame:
    df = pd.read_parquet(path(name))
    df.index = pd.DatetimeIndex(df.index).as_unit("ns")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df


def download_all(log=print) -> None:
    f = Fetcher()
    jobs = []
    for s in ASSETS:
        for tf in ("1h", "4h", "1d"):
            jobs.append((f"spot_{s}_{tf}", f"data/spot/monthly/klines/{s}/{tf}/", parse_klines))
            jobs.append((f"spot_{s}_{tf}_daily", f"data/spot/daily/klines/{s}/{tf}/{s}-{tf}-2026-", parse_klines))
        jobs.append((f"funding_{s}", f"data/futures/um/monthly/fundingRate/{s}/", parse_funding))
        jobs.append((f"premium_{s}_1d", f"data/futures/um/monthly/premiumIndexKlines/{s}/1d/", parse_klines))
        jobs.append((f"premium_{s}_4h", f"data/futures/um/monthly/premiumIndexKlines/{s}/4h/", parse_klines))
        jobs.append((f"metrics_{s}", f"data/futures/um/daily/metrics/{s}/", parse_metrics))
    for s in ("PAXGUSDT", "EURUSDT"):
        jobs.append((f"spot_{s}_1d", f"data/spot/monthly/klines/{s}/1d/", parse_klines))
        jobs.append((f"spot_{s}_1d_daily", f"data/spot/daily/klines/{s}/1d/{s}-1d-2026-", parse_klines))
    for name, prefix, parse in jobs:
        df = f.archive(prefix, parse)
        if len(df):
            save(df, name)
        log(f"  {name}: {len(df)} rows" + (f" {df.index[0]} .. {df.index[-1]}" if len(df) else ""))
    # merge daily-file tails (months whose monthly archive is not out yet) into the monthly series
    for name in [j[0] for j in jobs if j[0].endswith("_daily")]:
        base = name[: -len("_daily")]
        if path(name).exists() and path(base).exists():
            df = pd.concat([load(base), load(name)]).sort_index()
            save(df[~df.index.duplicated(keep="first")], base)
            path(name).unlink()
    for name, url in (("vix", VIX_URL), ("us10y_monthly", US10Y_MONTHLY_URL)):
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        raw = pd.read_csv(io.StringIO(r.text))
        raw.columns = [c.lower() for c in raw.columns]
        dcol = raw.columns[0]
        raw.index = pd.DatetimeIndex(pd.to_datetime(raw[dcol], utc=True)).as_unit("ns").rename("date")
        save(raw.drop(columns=[dcol]).astype(float), name)
        log(f"  {name}: {len(raw)} rows {raw.index[0].date()} .. {raw.index[-1].date()}")


# ----------------------------------------------------------------------------- point-in-time views
def known_at_close(df: pd.DataFrame, interval: str) -> pd.DataFrame:
    """Re-index klines by the time they become known (close time)."""
    out = df.copy()
    out.index = out.index + pd.Timedelta(interval.replace("d", "D"))
    return out


def vix_known() -> pd.Series:
    """VIX close of US date D, known from D+1 00:00 UTC."""
    v = load("vix")["close"]
    v.index = v.index.normalize() + pd.Timedelta(days=1)
    return v


def daily_asof(series: pd.Series, days: pd.DatetimeIndex) -> pd.Series:
    """Value known at the START (00:00 UTC) of each day in `days` (strictly earlier timestamps
    only; a value stamped exactly 00:00 counts as known)."""
    s = series.sort_index()
    pos = s.index.searchsorted(days, side="right") - 1
    vals = s.to_numpy(float)
    return pd.Series(np.where(pos >= 0, vals[np.clip(pos, 0, None)], np.nan), index=days)
