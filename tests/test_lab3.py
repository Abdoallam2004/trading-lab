import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from lab3 import data as d3
from lab3.engine import Bars, Costs, Order, simulate
from lab3.market import Market, pivots
from lab3.partA import expanding_percentile, gate_components
from lab3.setups import SETUPS, T2VolumeBreakout, T5EmaRsiEngulfing, T6BaseCrack
from lab3.wf import Lab, deflated_sharpe

ROOT = Path(__file__).resolve().parent.parent
TFS = {"1m": ("2021-01-01", "2021-01-12"), "5m": ("2020-12-01", "2021-01-12"),
       "15m": ("2020-09-01", "2021-01-12"), "1h": ("2019-12-01", "2021-01-12"),
       "4h": ("2019-01-01", "2021-01-12"), "1d": ("2017-08-17", "2021-01-12")}
FREQ = {"1m": "1min", "5m": "5min", "15m": "15min", "1h": "1h", "4h": "4h", "1d": "1D"}


def synth(tf, seed, start=None, end=None):
    a, b = TFS[tf]
    idx = pd.date_range(start or a, end or b, freq=FREQ[tf], tz="UTC", inclusive="left")
    rng = np.random.default_rng(seed)
    n = len(idx)
    vol = 0.004 * np.sqrt(pd.Timedelta(FREQ[tf]) / pd.Timedelta("1h"))
    regime = np.repeat(rng.choice([1.5, -1.0, 0.2], size=n // 300 + 1), 300)[:n] * vol * 0.05
    c = 100 * np.exp(np.cumsum(regime + vol * rng.standard_normal(n)))
    o = np.r_[c[0], c[:-1]] * (1 + vol * 0.2 * rng.standard_normal(n))
    h = np.maximum(o, c) * (1 + np.abs(vol * 0.6 * rng.standard_normal(n)))
    l = np.minimum(o, c) * (1 - np.abs(vol * 0.6 * rng.standard_normal(n)))
    v = rng.lognormal(10, 0.5, n) * (1 + 3 * (rng.random(n) < 0.03))
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v, "quote_volume": v * c,
                         "trades": 1.0}, index=idx.rename("open_time"))


@pytest.fixture(scope="module")
def frames():
    return {(a, tf): synth(tf, 10 * k + j) for k, a in enumerate(d3.ASSETS) for j, tf in enumerate(TFS)}


def cut(frames, until):
    """Keep only bars that have CLOSED by `until`."""
    return {k: f[f.index + d3.TF_DELTA[k[1]] <= until] for k, f in frames.items()}


def _r(x):
    return None if x is None or not np.isfinite(x) else round(float(x), 10)


def order_sig(m, S, p, rules):
    tf = S.sim_tf(p)
    idx = m.df("BTCUSDT", tf).index
    if S is T6BaseCrack:
        return [(idx[t], _r(P), _r(a)) for t, P, a in S.events(m, "BTCUSDT", p, frozenset(rules))]
    out = []
    for o in S.orders(m, "BTCUSDT", p, frozenset(rules)):
        out.append((idx[o.sig_idx], o.valid_from - o.sig_idx, o.valid_to - o.sig_idx, o.kind, *(_r(x) for x in
                    (o.limit, o.stop, o.stop_offset, o.target, o.target_r, o.cancel_below)), o.cap))
    return out


def cases():
    for S in SETUPS:
        p = S.grid()[0]
        for rules in ([], S.RULES):
            yield pytest.param(S, p, tuple(rules), id=f"{S.key}-{'all' if rules else 'bare'}")


CUT = pd.Timestamp("2021-01-09 13:00", tz="UTC")


# ----------------------------------------------------------------------------- look-ahead
@pytest.mark.parametrize("S,p,rules", list(cases()))
def test_append_one_bar_does_not_change_earlier_signals(frames, S, p, rules):
    tf = S.sim_tf(p)
    step = d3.TF_DELTA[tf] if tf != "1m" else pd.Timedelta(minutes=5)
    a = order_sig(Market(frames=cut(frames, CUT)), S, p, rules)
    b = order_sig(Market(frames=cut(frames, CUT + step)), S, p, rules)
    horizon = CUT - step  # includes signals on the last bar of the shorter data
    a = [x for x in a if x[0] <= horizon]
    b = [x for x in b if x[0] <= horizon]
    assert a == b


@pytest.mark.parametrize("S,p,rules", list(cases()))
def test_every_order_is_known_at_its_signal_close(frames, S, p, rules):
    """Recompute with the data ending exactly at each order's signal bar: the order must
    already exist with identical fields (any peek at a later bar would make it differ)."""
    tf = S.sim_tf(p)
    full = order_sig(Market(frames=frames), S, p, rules)
    assert full, "setup produced no signals on the synthetic data"
    for sig in full[:: max(1, len(full) // 60)][:60]:
        got = order_sig(Market(frames=cut(frames, sig[0] + d3.TF_DELTA[tf])), S, p, rules)
        assert sig in got, sig


@pytest.mark.parametrize("S,p,rules", list(cases()))
def test_shocking_a_close_never_changes_earlier_signals(frames, S, p, rules):
    """Shock the close (x0.9 / x1.1) of one bar on every timeframe: signals from earlier bars are unchanged."""
    t = pd.Timestamp("2021-01-08 12:00", tz="UTC")
    base = order_sig(Market(frames=frames), S, p, rules)
    for f in (0.9, 1.1):
        shocked = {}
        for k, df in frames.items():
            df = df.copy()
            pos = df.index.searchsorted(t)
            if pos < len(df):
                c = df.iloc[pos, df.columns.get_loc("close")] * f
                df.iloc[pos, df.columns.get_loc("close")] = c
                df.iloc[pos, df.columns.get_loc("high")] = max(df.iloc[pos]["high"], c)
                df.iloc[pos, df.columns.get_loc("low")] = min(df.iloc[pos]["low"], c)
            shocked[k] = df
        got = order_sig(Market(frames=shocked), S, p, rules)
        assert [x for x in got if x[0] < t] == [x for x in base if x[0] < t]


def test_no_centered_or_forward_functions_in_signal_code():
    """No filter may use centred / forward-looking operations."""
    banned = [r"filtfilt", r"center\s*=\s*True", r"\.shift\(\s*-", r"bfill", r"backfill", r"method\s*=\s*['\"]b",
              r"np\.roll\(", r"\[::-1\]", r"savgol", r"lowess", r"interpolate\("]
    files = ["lab3/market.py", "lab3/setups.py", "lab3/partA.py", "lab2/signals.py", "lab/indicators.py"]
    for f in files:
        src = (ROOT / f).read_text()
        for pat in banned:
            assert not re.search(pat, src), f"{f} uses forbidden pattern {pat}"


def test_pivots_are_only_known_after_confirmation():
    v = np.array([1, 2, 3, 9, 3, 2, 1, 2, 3], float)
    for k in (2, 3):
        hi = pivots(v, k, "high")
        assert np.flatnonzero(hi).tolist() == [3 + k]   # the peak at 3 is reported k bars later
        # and it does not exist yet when only the first 3+k bars are known
        assert not pivots(v[:3 + k], k, "high").any()


# ----------------------------------------------------------------------------- engine
def bars(rows):
    idx = pd.date_range("2021-01-01", periods=len(rows), freq="1h", tz="UTC")
    return Bars(pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx, dtype=float))


NOCOST = Costs(0.0, 0.0)
FLAT = (100, 101, 99, 100)


def test_market_stop_first_and_gap_fill():
    b = bars([FLAT, FLAT, (100, 115, 90, 100), (100, 101, 99, 100)])
    t = simulate(b, [Order(0, 1, 1, stop=95.0, target_r=2.0)], NOCOST)
    assert t.iloc[0]["reason"] == "stop"   # bar 2 touches both -> stop first
    b = bars([FLAT, FLAT, (90, 91, 88, 89)])
    t = simulate(b, [Order(0, 1, 1, stop=95.0, target_r=2.0)], NOCOST)
    assert t.iloc[0]["exit"] == 90 and t.iloc[0]["r"] == pytest.approx(-2.0)


def test_limit_fill_cancel_and_time_cap():
    b = bars([FLAT, (100, 100, 97, 98), (98, 106, 97.5, 105), FLAT])
    t = simulate(b, [Order(0, 1, 3, kind="limit", limit=98.0, stop=96.0, target=104.0)], NOCOST)
    assert t.iloc[0]["entry"] == 98 and t.iloc[0]["reason"] == "target"
    b = bars([FLAT, (100, 100, 99, 95), (95, 96, 90, 92)])
    t = simulate(b, [Order(0, 1, 2, kind="limit", limit=94.0, stop=90.0, target=110.0, cancel_below=96.0)], NOCOST)
    assert len(t) == 0   # closed below the zone before the limit was reached
    b = bars([FLAT] * 6)
    t = simulate(b, [Order(0, 1, 1, stop=90.0, target_r=2.0, cap=2)], NOCOST)
    assert t.iloc[0]["reason"] == "time" and t.iloc[0]["bars"] == 3


def test_sizing_risk_and_cash_cap_and_daily_limit():
    b = bars([FLAT, FLAT, (100, 100.5, 89, 90)] + [FLAT] * 10)
    t = simulate(b, [Order(0, 1, 1, stop=90.0, target_r=2.0)], NOCOST)
    assert t.iloc[0]["ret"] == pytest.approx(-0.015)            # 1.5% of equity at the stop
    t = simulate(bars([FLAT, FLAT, (100, 100.5, 99.4, 99.5)]), [Order(0, 1, 1, stop=99.5, target_r=2.0)], NOCOST)
    assert t.iloc[0]["ret"] == pytest.approx(-0.005)            # tight stop -> capped at 100% of cash
    orders = [Order(i, i + 1, i + 1, stop=50.0, target_r=0.001) for i in range(8)]
    t = simulate(bars([FLAT] * 10), orders, NOCOST)
    assert len(t) == 3                                          # max 3 entries per day


def test_costs_are_charged_on_every_fill():
    b = bars([FLAT, FLAT, (100, 104.1, 99.5, 104)])
    t = simulate(b, [Order(0, 1, 1, stop=98.0, target_r=2.0)], Costs())
    e_cost = 100 * 1.0005 * 1.001
    assert t.iloc[0]["r"] == pytest.approx((104 * 0.9995 * 0.999 - e_cost) / (e_cost - 98 * 0.9995 * 0.999))


# ----------------------------------------------------------------------------- walk-forward
def test_walk_forward_choices_ignore_test_window_data(frames):
    long = dict(frames)
    long[("BTCUSDT", "15m")] = synth("15m", 3, start="2019-12-01", end="2021-04-01")
    lab = Lab(Market(frames=long), log=lambda *_: None)
    wf = lab.walk_forward(T5EmaRsiEngulfing, [])
    assert wf.choices[0] is not None
    shocked = dict(long)
    f = long[("BTCUSDT", "15m")].copy()
    f.loc[f.index >= "2021-01-01", ["open", "high", "low", "close"]] *= 1.5  # change only the test window
    shocked[("BTCUSDT", "15m")] = f
    wf2 = Lab(Market(frames=shocked), log=lambda *_: None).walk_forward(T5EmaRsiEngulfing, [])
    assert wf2.choices[0] == wf.choices[0]


# ----------------------------------------------------------------------------- holdout lock
def test_holdout_is_locked(tmp_path):
    idx = pd.date_range("2025-09-28", "2025-10-03", freq="1D", tz="UTC")
    df = pd.DataFrame({c: 1.0 for c in ["open", "high", "low", "close", "volume", "quote_volume", "trades"]},
                      index=idx.rename("open_time"))
    from lab import data as lab1
    lab1.save(df, "BTCUSDT", "1d", tmp_path)
    dev = d3.load_bars("BTCUSDT", "1d", data_dir=tmp_path)
    assert dev.index[-1] <= d3.DEV_END
    full = d3.load_bars("BTCUSDT", "1d", holdout=True, data_dir=tmp_path)
    assert full.index[-1] > d3.DEV_END
    with pytest.raises(d3.HoldoutLocked):
        d3.assert_no_holdout(full)


# ----------------------------------------------------------------------------- Part A gate
def test_gate_is_point_in_time():
    rng = np.random.default_rng(0)
    idx = pd.date_range("2012-01-01", "2016-01-01", freq="1D", tz="UTC")
    price = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.001, 0.03, len(idx)))), idx)
    mvrv = pd.DataFrame({"mc": price * 1e7, "rc": price.rolling(150, min_periods=1).mean() * 1e7}, idx).shift(1).dropna()
    t = pd.Timestamp("2015-03-01", tz="UTC")
    full = gate_components(price, mvrv)
    part = gate_components(price.loc[:t], mvrv.loc[:t])
    pd.testing.assert_frame_equal(part, full.loc[:t])
    ep = expanding_percentile(price, min_obs=10)
    assert ep.iloc[:10].isna().iloc[:9].all() and 0 < ep.dropna().min() <= ep.dropna().max() <= 100


# ----------------------------------------------------------------------------- DSR
def test_deflated_sharpe_penalises_more_trials():
    rng = np.random.default_rng(1)
    r = rng.normal(0.15, 1.0, 400)
    few, many = deflated_sharpe(r, 5, 0.01), deflated_sharpe(r, 500, 0.01)
    assert 0 <= many < few <= 1
    assert np.isnan(deflated_sharpe(r, 1, 0.01))
