import numpy as np
import pandas as pd
import pytest

from lab4.phaseC import _asof, benjamini_hochberg, daily_signals, onsets


def test_asof_uses_only_values_published_by_then():
    ts = [pd.Timestamp(x, tz="UTC") for x in ("2022-01-01 08:00:00", "2022-01-01 16:00:00", "2022-01-02 00:00:01")]
    s = pd.Series([1.0, 2.0, 3.0], index=pd.DatetimeIndex(ts))
    when = pd.DatetimeIndex([pd.Timestamp(x, tz="UTC") for x in ("2022-01-01 07:59:00", "2022-01-01 16:00:00",
                                                                  "2022-01-02 00:00:00")])
    out = _asof(s, when)
    assert np.isnan(out[0]) and out[1] == 2.0 and out[2] == 2.0   # 00:00:01 is not known at 00:00


def synth_daily(n=700, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="1D", tz="UTC")
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.03, n)))
    d = pd.DataFrame({"open": c, "high": c * 1.02, "low": c * 0.98, "close": c,
                      "cvd": np.cumsum(rng.normal(0, 1, n)), "funding3": rng.normal(1e-4, 1e-4, n),
                      "funding1": rng.normal(1e-4, 1e-4, n), "oi": 1e9 * np.exp(np.cumsum(rng.normal(0, 0.02, n))),
                      "ls_ratio": rng.normal(1.5, 0.3, n), "premium": rng.normal(0, 1e-3, n)}, index=idx)
    d["btc_up"] = d["close"] > d["close"].rolling(200, min_periods=200).mean()
    return d


def test_daily_signals_do_not_change_when_a_day_is_appended():
    d = synth_daily()
    for cut in (400, 550, 650):
        a = daily_signals(d.iloc[:cut])
        b = daily_signals(d.iloc[:cut + 1])
        for k in a:
            assert list(a[k]) == [t for t in b[k] if t <= d.index[cut - 1]], k


def test_onsets_need_a_gap():
    idx = pd.date_range("2022-01-01", periods=20, freq="1D", tz="UTC")
    cond = pd.Series([True, False] * 10, index=idx)
    ev = onsets(cond, gap_days=7)
    assert all((b - a).days >= 7 for a, b in zip(ev, ev[1:]))


def test_benjamini_hochberg():
    p = np.array([0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, np.nan])
    out = benjamini_hochberg(p, 0.05)
    assert out.tolist()[:2] == [True, True] and not out[2:].any()


def test_vix_is_known_only_the_next_utc_day(monkeypatch):
    import lab4.data as d4
    idx = pd.DatetimeIndex([pd.Timestamp("2024-03-01", tz="UTC"), pd.Timestamp("2024-03-04", tz="UTC")])
    monkeypatch.setattr(d4, "load", lambda name: pd.DataFrame({"close": [15.0, 20.0]}, index=idx))
    v = d4.vix_known()
    assert list(v.index) == [pd.Timestamp("2024-03-02", tz="UTC"), pd.Timestamp("2024-03-05", tz="UTC")]
    # a strategy deciding on Monday 2024-03-04 (looks up the value as of 2024-03-03) sees Friday's 15, not 20
    assert v.asof(pd.Timestamp("2024-03-03", tz="UTC")) == 15.0
