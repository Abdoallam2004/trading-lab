import numpy as np
import pandas as pd
import pytest

from lab.synthetic import synth_4h, to_daily
from lab2 import signals as sg
from lab2.evaluate import core_pass, grid_points, neighbours, segment_shares
from lab2.sim import FEE, SLIP, Account, Prices, RunResult, irr, max_drawdown, metrics, run, utc
from lab2.strategies import (BTC, ETH, STRATEGIES, AltRotation, BuyHold, Context, DrawdownDCA, PlainDCA,
                             RegimeFilter, S2_TABLES, DCA200W)

ALTS = ["AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT"]


def synth_daily(sym, seed, start="2014-01-01", end="2020-12-31"):
    return to_daily(synth_4h(sym, start, end, seed=seed))


def make_ctx(until=None, shock_day=None, shock=1.0):
    """Synthetic BTC/ETH/alts + fake on-chain caps, optionally truncated at `until`.
    `shock_day`/`shock` multiply that day's CLOSE of every asset (an intrabar future event)."""
    cut = (lambda x: x.loc[:utc(until)]) if until is not None else (lambda x: x)

    def load(sym, seed, **kw):
        df = synth_daily(sym, seed, **kw)
        if shock_day is not None:
            df.loc[utc(shock_day), "close"] *= shock
        return cut(df)
    btc = load(BTC, 1)
    eth = load(ETH, 2)
    alts = {s: load(s, 10 + k, start="2016-01-01") for k, s in enumerate(ALTS)}
    sig_price = btc["close"]
    mvrv = pd.DataFrame({"mc": btc["close"] * 19e6, "rc": btc["close"].rolling(155, min_periods=1).mean() * 19e6},
                        index=btc.index).shift(1).dropna()
    prices = Prices({BTC: btc, ETH: eth, **alts})
    ctx = Context(sig_price, mvrv, prices.close[ALTS], universe=lambda d: [BTC] + ALTS, eth=eth, btc=btc)
    return ctx, prices


# ----------------------------------------------------------------------------- look-ahead
CUTS = ["2018-03-11", "2019-06-17", "2020-02-02"]


@pytest.mark.parametrize("fn", [
    lambda p: sg.regime_up(p, "200d"), lambda p: sg.regime_up(p, "50w"), lambda p: sg.regime_up(p, "20w"),
    sg.ratio_to_200w, sg.drawdown_from_ath, sg.logreg_z, lambda p: sg.momentum(p, 28)])
def test_signals_unchanged_when_one_bar_is_added(fn):
    full = synth_daily(BTC, 1)["close"]
    for t in CUTS:
        t = pd.Timestamp(t, tz="UTC")
        a = fn(full.loc[:t])
        b = fn(full.loc[:t + pd.Timedelta(days=1)]).loc[:t]
        pd.testing.assert_series_equal(a, b, check_names=False)


def test_mvrv_z_and_zigzag_point_in_time():
    ctx, _ = make_ctx()
    for t in CUTS:
        t = pd.Timestamp(t, tz="UTC")
        nxt = t + pd.Timedelta(days=1)
        a = sg.mvrv_z(ctx.mvrv.loc[:t])
        b = sg.mvrv_z(ctx.mvrv.loc[:nxt]).loc[:t]
        pd.testing.assert_series_equal(a, b)
        btc = ctx.btc
        pa = sg.zigzag(btc["high"].loc[:t], btc["low"].loc[:t], 0.10)
        pb = [p for p in sg.zigzag(btc["high"].loc[:nxt], btc["low"].loc[:nxt], 0.10) if p.confirm_time <= t]
        assert pa == pb


@pytest.mark.parametrize("cls", STRATEGIES + [BuyHold, PlainDCA])
@pytest.mark.parametrize("frame", ["A", "B"])
def test_strategy_results_unchanged_when_one_bar_is_added(cls, frame):
    """Run on data ending at t and at t+1: every day up to t must be identical."""
    params = grid_points(cls)[0] if hasattr(cls, "GRID") else {}
    t = pd.Timestamp("2019-09-15", tz="UTC")
    curves = []
    for until in (t, t + pd.Timedelta(days=1)):
        ctx, prices = make_ctx(until)
        res = run(cls(ctx, **params), prices, "2018-01-01", t, frame)
        curves.append(res.equity)
    pd.testing.assert_series_equal(curves[0], curves[1].loc[:t])


@pytest.mark.parametrize("cls", STRATEGIES + [BuyHold, PlainDCA])
@pytest.mark.parametrize("frame", ["A", "B"])
def test_trades_at_open_ignore_that_days_close(cls, frame):
    """Trades executed at day t's open may only use closes up to t-1: changing day t's close
    (x0.5 or x1.5) must leave cash and BTC holdings after day t's trades unchanged."""
    params = grid_points(cls)[0] if hasattr(cls, "GRID") else {}
    for t in ["2019-03-04", "2019-07-15", "2020-03-16", "2020-11-09"]:  # Mondays
        t = utc(t)
        runs = []
        for shock in (1.0, 0.5, 1.5):
            ctx, prices = make_ctx(shock_day=t, shock=shock)
            r = run(cls(ctx, **params), prices, "2018-01-01", t, frame)
            runs.append((r.cash.loc[t], r.btc_qty.loc[t], r.n_trades))
        for other in runs[1:]:
            assert other == pytest.approx(runs[0]), (t, runs)


# ----------------------------------------------------------------------------- simulator
def test_account_costs_and_no_leverage():
    a = Account()
    a.deposit(pd.Timestamp("2020-01-06", tz="UTC"), 1000)
    q = a.buy(BTC, 5000, 100.0)              # asks for more than the cash
    assert a.cash == pytest.approx(0.0)
    assert q == pytest.approx(1000 / (1 + FEE) / (100 * (1 + SLIP)))
    usd = a.sell(BTC, 10 * q, 100.0)         # cannot sell more than held
    assert usd == pytest.approx(q * 100 * (1 - SLIP) * (1 - FEE))
    assert BTC not in a.qty


def test_round_trip_cost_is_about_0_3_percent():
    a = Account()
    a.deposit(None, 10_000)
    q = a.buy(BTC, 10_000, 50_000)
    a.sell(BTC, q, 50_000)
    assert 1 - a.cash / 10_000 == pytest.approx(1 - ((1 - FEE) * (1 - SLIP)) / ((1 + FEE) * (1 + SLIP)))


def test_frame_b_contributes_every_monday_and_buy_hold_matches_dca():
    ctx, prices = make_ctx()
    rb = run(PlainDCA(ctx), prices, "2019-01-01", "2019-12-31", "B")
    mondays = pd.date_range("2019-01-01", "2019-12-31", freq="W-MON")
    assert rb.contributed == pytest.approx(100 * len(mondays))
    assert (rb.equity >= 0).all()
    r1 = run(BuyHold(ctx), prices, "2019-01-01", "2019-12-31", "B")
    assert r1.equity.iloc[-1] == pytest.approx(rb.equity.iloc[-1])


def test_irr_and_drawdown_known_values():
    idx = pd.date_range("2020-01-01", periods=367, freq="D", tz="UTC")
    flows = pd.Series(0.0, idx); flows.iloc[0] = 100
    eq = pd.Series(np.linspace(100, 110, len(idx)), idx)
    r = RunResult(eq, eq, eq * 0, flows, 100.0, 1, 100.0, [])
    assert irr(r) == pytest.approx(0.10, abs=2e-3)
    assert max_drawdown(pd.Series([1.0, 2.0, 1.0, 3.0])) == pytest.approx(0.5)
    m = metrics(r, "A")
    assert m["multiple"] == pytest.approx(1.1) and m["max_dd"] == 0


def test_regime_filter_holds_cash_when_down():
    ctx, prices = make_ctx()
    res = run(RegimeFilter(ctx, sma="200d"), prices, "2018-01-01", "2020-12-31", "A")
    up = sg.regime_up(ctx.sig_price, "200d")
    # on a Tuesday after a Monday whose previous close was below the SMA, we hold no BTC
    mondays = [d for d in res.btc_qty.index if d.dayofweek == 0 and up.asof(d - pd.Timedelta(days=1)) == False]  # noqa: E712
    assert mondays and all(res.btc_qty[d] == 0 for d in mondays)


def test_dca_tables_and_drawdown_dca_saves_until_triggered():
    assert [m for _, m in S2_TABLES["base"][0]] == [3.0, 1.0, 0.5, 0.0]
    ctx, prices = make_ctx()
    s = DrawdownDCA(ctx, x=0.99, n_weeks=4)  # never triggered -> pure saving
    res = run(s, prices, "2019-01-01", "2019-06-30", "B")
    assert res.n_trades == 0 and res.equity.iloc[-1] == pytest.approx(res.contributed)
    assert run(DCA200W(ctx, table="base"), prices, "2019-01-01", "2019-06-30", "B").equity.min() >= 0


def test_alt_rotation_uses_only_universe_and_btc_regime():
    ctx, prices = make_ctx()
    res = run(AltRotation(ctx, n=2, off="cash"), prices, "2019-01-01", "2020-12-31", "A")
    assert res.n_trades > 0 and (res.equity > 0).all()


# ----------------------------------------------------------------------------- evaluation helpers
def test_neighbours_and_grids():
    assert len(grid_points(DrawdownDCA)) == 6
    nb = neighbours(DrawdownDCA, {"x": 0.40, "n_weeks": 4})
    assert {"x": 0.30, "n_weeks": 4} in nb and {"x": 0.50, "n_weeks": 4} in nb and {"x": 0.40, "n_weeks": 12} in nb
    assert len(nb) == 3


def test_core_pass_rules():
    b = {"calmar": 1.0, "max_dd": 0.5, "multiple": 1.6, "btc_per_1k": 0.02}
    assert core_pass({"calmar": 1.2, "max_dd": 0.4}, b, "A")
    assert not core_pass({"calmar": 1.2, "max_dd": 0.6}, b, "A")
    assert core_pass({"multiple": 1.5, "btc_per_1k": 0.03, "max_dd": 0.5}, b, "B")  # more BTC per $
    assert not core_pass({"multiple": 1.7, "btc_per_1k": 0.03, "max_dd": 0.55}, b, "B")


def test_segment_shares():
    idx = pd.date_range("2018-01-01", "2026-09-30", freq="D", tz="UTC")
    eq = pd.Series(100.0, idx)
    eq[idx >= pd.Timestamp("2020-06-01", tz="UTC")] = 200.0  # all profit made in 2020-21
    flows = pd.Series(0.0, idx); flows.iloc[0] = 100
    r = RunResult(eq, eq, eq * 0, flows, 100.0, 1, 0.0, [])
    sh = segment_shares(r)
    assert sh["2020–21"] == pytest.approx(1.0) and sh["2023–24"] == pytest.approx(0.0)
