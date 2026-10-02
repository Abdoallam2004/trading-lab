"""Download Binance spot klines from data.binance.vision and cache them as parquet.

Layout of the public archive:
  data/spot/monthly/klines/{SYM}/{TF}/{SYM}-{TF}-{YYYY}-{MM}.zip   (complete months)
  data/spot/daily/klines/{SYM}/{TF}/{SYM}-{TF}-{YYYY}-{MM}-{DD}.zip (recent days)

Each zip holds one headerless CSV (some newer files have a header). Since
2025-01-01 spot timestamps are in microseconds instead of milliseconds.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

from .config import DATA_DIR, QUOTE, START_DATE, TOP_N
from .universe import exclusion_reason

log = logging.getLogger(__name__)

BASE_URL = "https://data.binance.vision"
LISTING_URL = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
MIRROR_URL = LISTING_URL  # the S3 bucket behind data.binance.vision serves the same files
API_URL = "https://api.binance.com"

KLINE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore",
]
KEEP = ["open", "high", "low", "close", "volume", "quote_volume", "trades"]


# --------------------------------------------------------------------------- parsing
def _to_datetime(ts: pd.Series) -> pd.DatetimeIndex:
    ts = ts.astype("int64")
    # microseconds (>= 1e15) vs milliseconds
    unit_us = ts > 10**14
    ms = ts.where(~unit_us, ts // 1000)
    return pd.to_datetime(ms, unit="ms", utc=True)


def parse_klines_csv(raw: bytes | str) -> pd.DataFrame:
    """Parse one kline CSV (with or without header) into a clean OHLCV frame."""
    text = raw.decode() if isinstance(raw, bytes) else raw
    if not text.strip():
        return empty_frame()
    first = text.lstrip().split(",", 1)[0]
    header = 0 if not first.strip().lstrip("-").isdigit() else None
    df = pd.read_csv(io.StringIO(text), header=header)
    df = df.iloc[:, : len(KLINE_COLUMNS)]
    df.columns = KLINE_COLUMNS[: df.shape[1]]
    idx = _to_datetime(df["open_time"])
    out = df[KEEP].astype("float64")
    out.index = pd.DatetimeIndex(idx, name="open_time")
    return out


def parse_klines_zip(content: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        frames = [parse_klines_csv(zf.read(name)) for name in zf.namelist() if name.endswith(".csv")]
    return pd.concat(frames).sort_index() if frames else empty_frame()


def parse_api_klines(rows: list[list]) -> pd.DataFrame:
    """Parse /api/v3/klines JSON rows (same column order as the archive)."""
    if not rows:
        return empty_frame()
    df = pd.DataFrame([r[: len(KLINE_COLUMNS)] for r in rows], columns=KLINE_COLUMNS)
    out = df[KEEP].astype("float64")
    out.index = pd.DatetimeIndex(_to_datetime(df["open_time"]), name="open_time")
    return out


def empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=KEEP, dtype="float64", index=pd.DatetimeIndex([], tz="UTC", name="open_time"))


def parse_listing_xml(xml_text: str) -> tuple[list[str], str | None]:
    """Parse an S3 ListBucket page -> (symbol names, next marker or None)."""
    root = ET.fromstring(xml_text)
    ns = {"s3": root.tag.split("}")[0].strip("{")} if root.tag.startswith("{") else {}
    find = (lambda e, t: e.find(f"s3:{t}", ns)) if ns else (lambda e, t: e.find(t))
    findall = (lambda e, t: e.findall(f"s3:{t}", ns)) if ns else (lambda e, t: e.findall(t))
    symbols = []
    for cp in findall(root, "CommonPrefixes"):
        prefix = find(cp, "Prefix").text  # data/spot/monthly/klines/BTCUSDT/
        symbols.append(prefix.rstrip("/").split("/")[-1])
    truncated = find(root, "IsTruncated")
    next_marker = None
    if truncated is not None and truncated.text == "true":
        nm = find(root, "NextMarker")
        next_marker = nm.text if nm is not None else (prefix if symbols else None)
    return symbols, next_marker


def parse_keys_xml(xml_text: str) -> tuple[list[str], str | None]:
    """Parse an S3 ListBucket page without delimiter -> (object keys, next marker or None)."""
    root = ET.fromstring(xml_text)
    ns = root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""
    keys = [c.find(f"{ns}Key").text for c in root.findall(f"{ns}Contents")]
    truncated = root.find(f"{ns}IsTruncated")
    more = truncated is not None and truncated.text == "true"
    return keys, (keys[-1] if more and keys else None)


# --------------------------------------------------------------------------- urls
def monthly_url(symbol: str, interval: str, year: int, month: int) -> str:
    return (f"{BASE_URL}/data/spot/monthly/klines/{symbol}/{interval}/"
            f"{symbol}-{interval}-{year:04d}-{month:02d}.zip")


def daily_url(symbol: str, interval: str, day: date) -> str:
    return (f"{BASE_URL}/data/spot/daily/klines/{symbol}/{interval}/"
            f"{symbol}-{interval}-{day:%Y-%m-%d}.zip")


def month_range(start: date, end: date) -> list[tuple[int, int]]:
    """All (year, month) from start's month to end's month inclusive."""
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def daily_urls_for_month(symbol: str, interval: str, year: int, month: int, start: date, today: date) -> list[str]:
    day = max(date(year, month, 1), start)
    out = []
    while day.month == month and day < today:
        out.append(daily_url(symbol, interval, day))
        day += timedelta(days=1)
    return out


def plan_urls(symbol: str, interval: str, start: date, today: date,
              available: set[str] | None = None) -> list[str]:
    """Monthly files for complete months, daily files for the current month up to yesterday.

    `available` (from an S3 listing) filters out files that do not exist. A month whose
    monthly file is not published yet (the archive lags a few days after month end) is
    replaced by its daily files.
    """
    first_of_month = today.replace(day=1)
    last_complete = first_of_month - timedelta(days=1)
    urls = []
    months = month_range(start, last_complete) if start <= last_complete else []
    have_monthly = [ym for ym in months if available is None or monthly_url(symbol, interval, *ym) in available]
    last_monthly = max(have_monthly) if have_monthly else None
    for ym in months:
        if ym in have_monthly:
            urls.append(monthly_url(symbol, interval, *ym))
        elif available is not None and (last_monthly is None or ym > last_monthly):
            urls += daily_urls_for_month(symbol, interval, *ym, start, today)  # not published yet
    urls += daily_urls_for_month(symbol, interval, first_of_month.year, first_of_month.month, start, today)
    if available is not None:
        urls = [u for u in urls if u in available]
    return urls


# --------------------------------------------------------------------------- network
class Downloader:
    def __init__(self, session: requests.Session | None = None, verify_checksum: bool = False,
                 timeout: float = 30.0, retries: int = 3):
        if session is None:
            session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(pool_connections=8, pool_maxsize=64)
            session.mount("https://", adapter)
        self.session = session
        self.verify_checksum = verify_checksum
        self.timeout = timeout
        self.retries = retries
        self.use_mirror = False

    def _resolve(self, url: str) -> str:
        if self.use_mirror and url.startswith(BASE_URL):
            return MIRROR_URL + url[len(BASE_URL):]
        return url

    def get(self, url: str) -> bytes | None:
        """GET bytes; None on 404 (file does not exist, e.g. coin not listed yet).

        If data.binance.vision itself is unreachable (DNS, firewall, proxy), switch to the
        S3 bucket that backs it.
        """
        last_err = None
        for _ in range(self.retries + 1):
            try:
                r = self.session.get(self._resolve(url), timeout=self.timeout)
                if r.status_code in (403, 404) and self.use_mirror:
                    return None  # S3 answers 403 for missing keys on some buckets
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                return r.content
            except requests.ConnectionError as e:
                last_err = e
                if not self.use_mirror and url.startswith(BASE_URL):
                    log.warning("data.binance.vision unreachable, using S3 mirror %s", MIRROR_URL)
                    self.use_mirror = True
            except requests.RequestException as e:  # retry transient errors
                last_err = e
        raise RuntimeError(f"failed to download {url}: {last_err}")

    def list_keys(self, prefix: str) -> list[str]:
        keys, marker = [], None
        while True:
            params = {"prefix": prefix}
            if marker:
                params["marker"] = marker
            r = self.session.get(LISTING_URL, params=params, timeout=self.timeout)
            r.raise_for_status()
            page, marker = parse_keys_xml(r.text)
            keys += page
            if not marker:
                return keys

    def available_urls(self, symbol: str, interval: str, months: list[tuple[int, int]]) -> set[str] | None:
        """URLs of the monthly files plus the daily files of `months`; None if listing fails."""
        try:
            keys = self.list_keys(f"data/spot/monthly/klines/{symbol}/{interval}/")
            for y, m in months:
                keys += self.list_keys(f"data/spot/daily/klines/{symbol}/{interval}/{symbol}-{interval}-{y:04d}-{m:02d}")
        except requests.RequestException as e:
            log.warning("S3 listing failed (%s); downloading blind", e)
            return None
        return {f"{BASE_URL}/{k}" for k in keys if k.endswith(".zip")}

    def get_zip_frame(self, url: str) -> pd.DataFrame | None:
        content = self.get(url)
        if content is None:
            return None
        if self.verify_checksum:
            chk = self.get(url + ".CHECKSUM")
            if chk is not None:
                expected = chk.decode().split()[0]
                actual = hashlib.sha256(content).hexdigest()
                if expected != actual:
                    raise RuntimeError(f"checksum mismatch for {url}")
        return parse_klines_zip(content)

    def list_symbols(self, quote: str = QUOTE) -> list[str]:
        prefix = "data/spot/monthly/klines/"
        symbols, marker = [], None
        while True:
            params = {"delimiter": "/", "prefix": prefix}
            if marker:
                params["marker"] = marker
            r = self.session.get(LISTING_URL, params=params, timeout=self.timeout)
            r.raise_for_status()
            page, marker = parse_listing_xml(r.text)
            symbols += page
            if not marker:
                break
        return sorted(s for s in set(symbols) if s.endswith(quote))


# --------------------------------------------------------------------------- cache
def cache_path(symbol: str, interval: str, data_dir: Path = DATA_DIR) -> Path:
    return Path(data_dir) / interval / f"{symbol}.parquet"


def load(symbol: str, interval: str, data_dir: Path = DATA_DIR) -> pd.DataFrame:
    path = cache_path(symbol, interval, data_dir)
    if not path.exists():
        raise FileNotFoundError(f"no cached data for {symbol} {interval}: run scripts/download_data.py")
    df = pd.read_parquet(path)
    df.index = pd.DatetimeIndex(df.index, name="open_time")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df


def save(df: pd.DataFrame, symbol: str, interval: str, data_dir: Path = DATA_DIR) -> Path:
    path = cache_path(symbol, interval, data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)
    return path


def merge_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    frames = [f for f in frames if f is not None and len(f)]
    if not frames:
        return empty_frame()
    df = pd.concat(frames)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def update_symbol(symbol: str, interval: str, dl: Downloader, start: str = START_DATE,
                  today: date | None = None, data_dir: Path = DATA_DIR, workers: int = 8) -> pd.DataFrame:
    """Download missing files for a symbol and merge into the parquet cache (incremental)."""
    today = today or datetime.now(timezone.utc).date()
    start_d = pd.Timestamp(start).date()
    existing = None
    path = cache_path(symbol, interval, data_dir)
    if path.exists():
        existing = load(symbol, interval, data_dir)
        if len(existing):
            # re-fetch from the month of the last cached bar onwards
            start_d = max(start_d, existing.index[-1].date().replace(day=1))
    first = today.replace(day=1)
    prev = first - timedelta(days=1)
    recent = [(prev.year, prev.month), (first.year, first.month)]
    available = dl.available_urls(symbol, interval, recent) if hasattr(dl, "available_urls") else None
    urls = plan_urls(symbol, interval, start_d, today, available)
    if available is None:
        # no listing: if last month's monthly file is missing, fall back to its daily files
        last = monthly_url(symbol, interval, prev.year, prev.month)
        if last in urls and dl.get_zip_frame(last) is None:
            urls.remove(last)
            urls += daily_urls_for_month(symbol, interval, prev.year, prev.month, start_d, today)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        frames = list(ex.map(dl.get_zip_frame, urls))
    df = merge_frames([existing] + frames)
    df = df[df.index >= pd.Timestamp(start, tz="UTC")]
    if len(df):
        save(df, symbol, interval, data_dir)
    return df


def published_month(dl: Downloader, today: date | None = None, probe: str = "BTCUSDT") -> date:
    """Last month whose monthly archive exists. Month M is published a few days into M+1,
    so early in a month this falls back to the month before."""
    today = today or datetime.now(timezone.utc).date()
    last_month = today.replace(day=1) - timedelta(days=1)
    if dl.get(monthly_url(probe, "1d", last_month.year, last_month.month)) is not None:
        return last_month.replace(day=1)
    return (last_month.replace(day=1) - timedelta(days=1)).replace(day=1)


def rank_by_quote_volume(symbols: list[str], dl: Downloader, today: date | None = None,
                         workers: int = 16) -> pd.Series:
    """Rank symbols by USDT volume over the last *published* month (daily klines).
    Every symbol is measured on the same month, so a coin delisted last month scores 0."""
    m = published_month(dl, today)

    def vol(sym: str) -> float:
        df = dl.get_zip_frame(monthly_url(sym, "1d", m.year, m.month))
        return float(df["quote_volume"].sum()) if df is not None and len(df) else 0.0

    with ThreadPoolExecutor(max_workers=workers) as ex:
        vols = list(ex.map(vol, symbols))
    s = pd.Series(vols, index=symbols, name="quote_volume_usdt")
    return s[s > 0].sort_values(ascending=False)


def select_universe(all_symbols: list[str], volumes: pd.Series, top_n: int = TOP_N) -> list[str]:
    eligible = [s for s in volumes.index if s in set(all_symbols) and exclusion_reason(s) is None]
    return eligible[:top_n]


def universe_path(data_dir: Path = DATA_DIR) -> Path:
    return Path(data_dir) / "universe.json"


def save_universe(symbols: list[str], volumes: pd.Series, data_dir: Path = DATA_DIR,
                  source: str = "binance") -> None:
    path = universe_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source,
        "symbols": symbols,
        "quote_volume_usdt": {s: float(volumes.get(s, 0.0)) for s in symbols},
    }
    path.write_text(json.dumps(payload, indent=2))


def load_universe(data_dir: Path = DATA_DIR) -> dict:
    path = universe_path(data_dir)
    if not path.exists():
        raise FileNotFoundError("no universe.json: run scripts/download_data.py first")
    return json.loads(path.read_text())


def fetch_recent_api(symbol: str, interval: str, limit: int = 300,
                     session: requests.Session | None = None) -> pd.DataFrame:
    """Latest klines from the public REST API (fresher than the archive, used by the scanner)."""
    s = session or requests.Session()
    r = s.get(f"{API_URL}/api/v3/klines", params={"symbol": symbol, "interval": interval, "limit": limit},
              timeout=30)
    r.raise_for_status()
    return parse_api_klines(r.json())


def drop_unclosed(df: pd.DataFrame, interval: str, now: pd.Timestamp | None = None) -> pd.DataFrame:
    """Remove the last bar if it has not closed yet."""
    now = now or pd.Timestamp.now(tz="UTC")
    delta = pd.Timedelta(interval.replace("d", "D"))
    return df[df.index + delta <= now]
