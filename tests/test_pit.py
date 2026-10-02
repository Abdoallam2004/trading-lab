import numpy as np
import pandas as pd

from lab.pit import PointInTimeUniverse, rank_point_in_time
from lab.synthetic import synth_4h, to_daily
from lab.walkforward import Market, walk_forward


def vol(start, end, level):
    idx = pd.date_range(start, end, freq="1D", tz="UTC", inclusive="left")
    return pd.Series(level, index=idx, dtype=float)


VOLS = {
    "BTCUSDT": vol("2019-10-01", "2026-01-01", 100),
    "LUNAUSDT": vol("2020-08-01", "2022-05-20", 500),     # big, then delisted
    "SUIUSDT": vol("2023-05-03", "2026-01-01", 300),      # listed later
    "DOGEUSDT": vol("2019-10-01", "2026-01-01", 1000),    # meme: always excluded
    "ETHUSDT": vol("2019-10-01", "2026-01-01", 50),
}


def test_delisted_coin_included_while_it_existed():
    assert rank_point_in_time(VOLS, "2022-01-01", top_n=2) == ["LUNAUSDT", "BTCUSDT"]
    assert "LUNAUSDT" not in rank_point_in_time(VOLS, "2023-01-01")


def test_coin_listed_later_not_in_earlier_universe():
    assert "SUIUSDT" not in rank_point_in_time(VOLS, "2023-01-01")
    assert "SUIUSDT" not in rank_point_in_time(VOLS, "2023-05-10")   # < 20 days of history
    assert rank_point_in_time(VOLS, "2024-01-01")[0] == "SUIUSDT"


def test_uses_only_prior_three_months():
    v = {"AUSDT": pd.concat([vol("2020-01-01", "2020-06-01", 1), vol("2020-06-01", "2021-01-01", 100)]),
         "BUSDT": vol("2020-01-01", "2021-01-01", 10)}
    assert rank_point_in_time(v, "2020-06-01", top_n=1) == ["BUSDT"]   # A's spike starts on D: not known
    assert rank_point_in_time(v, "2020-09-01", top_n=1) == ["AUSDT"]


def test_exclusions_apply():
    assert "DOGEUSDT" not in rank_point_in_time(VOLS, "2021-01-01")


def test_universe_memo_and_monthly():
    u = PointInTimeUniverse(VOLS, top_n=3)
    m = u.monthly("2022-01-01", "2022-03-15")
    assert list(m) == ["2022-01-01", "2022-02-01", "2022-03-01"]
    assert u(pd.Timestamp("2022-01-01", tz="UTC")) == m["2022-01-01"]
    # naive start + tz-aware end (as in download_data.py) must work
    assert list(u.monthly("2022-01-01", pd.Timestamp("2022-02-10", tz="UTC"))) == ["2022-01-01", "2022-02-01"]


def test_walk_forward_trades_only_point_in_time_universe():
    frames = {"1d": {}}
    for k, s in enumerate(["BTCUSDT", "ETHUSDT", "SOLUSDT"]):
        frames["1d"][s] = to_daily(synth_4h(s, "2020-01-01", "2024-01-01", seed=k))
    market = Market(frames)
    # SOL is "not yet listed" before 2023 for the universe function
    def universe_at(d):
        return ["BTCUSDT", "ETHUSDT"] + (["SOLUSDT"] if pd.Timestamp(d) >= pd.Timestamp("2023-01-01", tz="UTC") else [])
    res = walk_forward(market, strategies=["PULLBACK"], timeframes=["1d"], train_months=24, test_months=12,
                       progress=lambda s: None, universe_at=universe_at, data_start="2020-01-01")
    t = res[0].oos_trades
    if len(t):
        early = t[t["entry_time"] < pd.Timestamp("2023-01-01", tz="UTC")]
        assert "SOLUSDT" not in set(early["symbol"])
    full = res[0].spec_full_trades
    if len(full):
        assert "SOLUSDT" not in set(full[full["entry_time"] < pd.Timestamp("2023-01-01", tz="UTC")]["symbol"])
