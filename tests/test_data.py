import io
import zipfile
from datetime import date

import pandas as pd
import pytest

from lab import data

ROW_MS = "1577836800000,7195.24,7255.0,7175.15,7200.85,16792.38,1577923199999,121214452.11,194010,8946.95,64597785.21,0"
ROW_US = "1735689600000000,93576.0,95151.15,92888.0,94591.79,10373.32,1735775999999999,975000000.0,1500000,5000.0,470000000.0,0"


def _zip(text: str, name="x.csv") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name, text)
    return buf.getvalue()


def test_parse_ms_and_us_timestamps():
    df = data.parse_klines_csv(ROW_MS + "\n" + ROW_US + "\n")
    assert list(df.index) == [pd.Timestamp("2020-01-01", tz="UTC"), pd.Timestamp("2025-01-01", tz="UTC")]
    assert df["close"].iloc[0] == pytest.approx(7200.85)
    assert list(df.columns) == data.KEEP


def test_parse_with_header():
    header = ",".join(data.KLINE_COLUMNS)
    df = data.parse_klines_csv(header + "\n" + ROW_MS + "\n")
    assert len(df) == 1 and df["open"].iloc[0] == pytest.approx(7195.24)


def test_parse_zip():
    df = data.parse_klines_zip(_zip(ROW_MS + "\n"))
    assert len(df) == 1


def test_parse_api_rows():
    rows = [[1577836800000, "1", "2", "0.5", "1.5", "10", 1577923199999, "15", 5, "1", "1", "0"]]
    df = data.parse_api_klines(rows)
    assert df["high"].iloc[0] == 2.0


def test_plan_urls_monthly_then_daily():
    urls = data.plan_urls("BTCUSDT", "1d", date(2025, 11, 1), date(2026, 1, 3))
    assert urls[0].endswith("monthly/klines/BTCUSDT/1d/BTCUSDT-1d-2025-11.zip")
    assert urls[1].endswith("BTCUSDT-1d-2025-12.zip")
    assert urls[2].endswith("daily/klines/BTCUSDT/1d/BTCUSDT-1d-2026-01-01.zip")
    assert urls[-1].endswith("2026-01-02.zip")  # today's file is not published yet
    assert len(urls) == 4


def test_listing_xml_pagination():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
      <IsTruncated>true</IsTruncated>
      <NextMarker>data/spot/monthly/klines/ETHUSDT/</NextMarker>
      <CommonPrefixes><Prefix>data/spot/monthly/klines/BTCUSDT/</Prefix></CommonPrefixes>
      <CommonPrefixes><Prefix>data/spot/monthly/klines/ETHUSDT/</Prefix></CommonPrefixes>
    </ListBucketResult>"""
    syms, marker = data.parse_listing_xml(xml)
    assert syms == ["BTCUSDT", "ETHUSDT"]
    assert marker == "data/spot/monthly/klines/ETHUSDT/"


class FakeResp:
    def __init__(self, status, content=b""):
        self.status_code, self.content = status, content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise data.requests.HTTPError(str(self.status_code))


class FakeSession:
    """Serves one daily bar per month file; 404 for anything else."""

    def __init__(self):
        self.calls = []

    def get(self, url, timeout=None, params=None):
        self.calls.append(url)
        if "/monthly/" in url and url.endswith(".zip"):
            ym = url.rsplit("-", 2)
            y, m = int(ym[-2]), int(ym[-1][:2])
            ts = int(pd.Timestamp(year=y, month=m, day=1, tz="UTC").timestamp() * 1000)
            row = f"{ts},1,2,0.5,1.5,10,{ts + 86399999},15,5,1,1,0\n"
            return FakeResp(200, _zip(row))
        return FakeResp(404)


def test_update_symbol_caches_parquet_and_is_incremental(tmp_path):
    sess = FakeSession()
    dl = data.Downloader(session=sess)
    df = data.update_symbol("BTCUSDT", "1d", dl, start="2025-01-01", today=date(2025, 6, 10),
                            data_dir=tmp_path, workers=2)
    assert len(df) == 5  # Jan..May monthly files, June daily files 404
    assert data.cache_path("BTCUSDT", "1d", tmp_path).exists()
    sess.calls.clear()
    df2 = data.update_symbol("BTCUSDT", "1d", dl, start="2025-01-01", today=date(2025, 7, 2),
                             data_dir=tmp_path, workers=2)
    assert len(df2) == 6
    assert not any("2025-01" in c for c in sess.calls)  # did not re-download old months
    loaded = data.load("BTCUSDT", "1d", tmp_path)
    assert loaded.index.tz is not None and len(loaded) == 6


def test_select_universe_respects_exclusions():
    vols = pd.Series({"USDCUSDT": 9e9, "BTCUSDT": 8e9, "DOGEUSDT": 7e9, "ETHUSDT": 6e9, "SOLUSDT": 5e9})
    assert data.select_universe(list(vols.index), vols, top_n=2) == ["BTCUSDT", "ETHUSDT"]


def test_drop_unclosed():
    idx = pd.date_range("2026-01-01", periods=3, freq="4h", tz="UTC")
    df = pd.DataFrame({"close": [1, 2, 3]}, index=idx)
    out = data.drop_unclosed(df, "4h", now=pd.Timestamp("2026-01-01 10:00", tz="UTC"))
    assert len(out) == 2


def test_plan_urls_uses_daily_files_when_last_month_not_published():
    today = date(2026, 10, 2)
    avail = {data.monthly_url("BTCUSDT", "1d", 2026, m) for m in (7, 8)}          # September missing
    avail |= {data.daily_url("BTCUSDT", "1d", date(2026, 9, d)) for d in range(1, 31)}
    avail |= {data.daily_url("BTCUSDT", "1d", date(2026, 10, 1))}
    urls = data.plan_urls("BTCUSDT", "1d", date(2026, 7, 1), today, avail)
    assert urls[:2] == [data.monthly_url("BTCUSDT", "1d", 2026, 7), data.monthly_url("BTCUSDT", "1d", 2026, 8)]
    assert sum("daily" in u and "2026-09-" in u for u in urls) == 30
    assert urls[-1].endswith("2026-10-01.zip")


def test_plan_urls_skips_months_before_listing():
    avail = {data.monthly_url("NEWUSDT", "1d", 2024, m) for m in (5, 6)}
    urls = data.plan_urls("NEWUSDT", "1d", date(2024, 1, 1), date(2024, 7, 15), avail)
    assert urls == sorted(avail)


class MonthDL:
    """get/get_zip_frame stub: has data for the months in `months` only."""

    def __init__(self, months, vols):
        self.months, self.vols = months, vols

    def get(self, url):
        return b"x" if any(f"-{m}.zip" in url for m in self.months) else None

    def get_zip_frame(self, url):
        sym = url.split("/klines/")[1].split("/")[0]
        if not self.get(url) or sym not in self.vols:
            return None
        return pd.DataFrame({"quote_volume": [self.vols[sym]]})


def test_rank_falls_back_to_previous_month_when_archive_not_published():
    dl = MonthDL(["2026-08"], {"BTCUSDT": 5.0, "ETHUSDT": 3.0})
    ranked = data.rank_by_quote_volume(["ETHUSDT", "BTCUSDT"], dl, today=date(2026, 10, 2), workers=1)
    assert list(ranked.index) == ["BTCUSDT", "ETHUSDT"]
    dl2 = MonthDL(["2026-09"], {"BTCUSDT": 5.0})
    assert data.published_month(dl2, date(2026, 10, 2)) == date(2026, 9, 1)


def test_parse_keys_xml():
    xml = """<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/"><IsTruncated>true</IsTruncated>
    <Contents><Key>data/spot/monthly/klines/BTCUSDT/1d/BTCUSDT-1d-2020-01.zip</Key></Contents>
    <Contents><Key>data/spot/monthly/klines/BTCUSDT/1d/BTCUSDT-1d-2020-01.zip.CHECKSUM</Key></Contents>
    </ListBucketResult>"""
    keys, marker = data.parse_keys_xml(xml)
    assert len(keys) == 2 and marker == keys[-1]


def test_downloader_switches_to_mirror_when_host_blocked():
    class Blocked:
        def __init__(self):
            self.urls = []

        def get(self, url, timeout=None, params=None):
            self.urls.append(url)
            if url.startswith(data.BASE_URL):
                raise data.requests.ConnectionError("blocked")
            return FakeResp(200, b"ok")

    sess = Blocked()
    dl = data.Downloader(session=sess)
    assert dl.get(data.monthly_url("BTCUSDT", "1d", 2024, 1)) == b"ok"
    assert sess.urls[-1].startswith(data.MIRROR_URL) and dl.use_mirror
