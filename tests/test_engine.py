import numpy as np
import pandas as pd
import pytest

from lab.config import CostModel, RiskModel
from lab.engine import ExitConfig, Setup, SymbolData, run_portfolio, simulate_trade, truncate_trade
from lab.metrics import max_drawdown, profit_factor

NOCOST = CostModel(fee_rate=0.0, slippage=0.0)


def bars(rows, start="2022-01-01", atr=1.0):
    """rows: list of (open, high, low, close)."""
    idx = pd.date_range(start, periods=len(rows), freq="1D", tz="UTC", name="open_time")
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx, dtype=float)
    df["atr"] = atr
    return df


FLAT = (100, 101, 99, 100)


def sd_of(rows, sym="AAAUSDT", **kw):
    return SymbolData(sym, bars(rows, **kw))


def test_stop_fill_at_stop_level():
    sd = sd_of([FLAT, FLAT, (100, 100.5, 94, 95), FLAT])
    tr = simulate_trade(sd, 0, 95.0, ExitConfig("2R"), NOCOST)
    assert tr.entry_idx == 1 and tr.entry_price == 100
    assert [(f.price, f.reason) for f in tr.fills] == [(95.0, "stop")]


def test_gap_through_stop_fills_at_open():
    sd = sd_of([FLAT, FLAT, (90, 91, 88, 89)])
    tr = simulate_trade(sd, 0, 95.0, ExitConfig("2R"), NOCOST)
    assert tr.fills[0].price == 90


def test_target_2r_with_costs():
    costs = CostModel(fee_rate=0.001, slippage=0.0005)
    sd = sd_of([FLAT, FLAT, (100, 115, 99.5, 112)])
    tr = simulate_trade(sd, 0, 95.0, ExitConfig("2R"), costs)
    entry = 100 * 1.0005
    assert tr.entry_price == pytest.approx(entry)
    target = entry + 2 * (entry - 95)
    assert tr.fills[0].price == pytest.approx(target * (1 - 0.0005))
    assert tr.fills[0].reason == "target_2R"


def test_stop_first_when_bar_hits_both():
    sd = sd_of([FLAT, FLAT, (100, 120, 90, 110)])
    tr = simulate_trade(sd, 0, 95.0, ExitConfig("2R"), NOCOST)
    assert tr.fills[0].reason == "stop"


def test_scale_out_then_breakeven():
    sd = sd_of([FLAT, FLAT, (100, 111, 99.5, 108), (108, 108, 99, 100)])
    tr = simulate_trade(sd, 0, 95.0, ExitConfig("2R_3R"), NOCOST)
    assert [(f.frac, f.reason) for f in tr.fills] == [(0.5, "target_2R"), (0.5, "breakeven")]
    assert tr.fills[0].price == 110 and tr.fills[1].price == 100


def test_trailing_stop_locks_profit():
    rows = [FLAT, FLAT] + [(100 + 5 * k, 101 + 5 * k, 99 + 5 * k, 100 + 5 * k) for k in range(1, 8)]
    rows += [(130, 130, 100, 101)]
    sd = sd_of(rows, atr=2.0)
    tr = simulate_trade(sd, 0, 95.0, ExitConfig("trail", 3.0), NOCOST)
    assert tr.fills[0].reason == "trail_stop"
    assert tr.fills[0].price == pytest.approx(136 - 6)  # highest high 136 - 3*ATR(2)


def test_invalid_when_open_below_stop():
    sd = sd_of([FLAT, (94, 95, 93, 94)])
    assert simulate_trade(sd, 0, 95.0, ExitConfig("2R"), NOCOST) is None


def test_end_of_data_closes_at_last_close():
    sd = sd_of([FLAT, FLAT, (100, 102, 99, 101)])
    tr = simulate_trade(sd, 0, 95.0, ExitConfig("3R"), NOCOST)
    assert tr.fills[-1].reason == "end_of_data" and tr.fills[-1].price == 101


def test_truncate_at_window_end():
    sd = sd_of([FLAT, FLAT, (100, 102, 99, 101), (101, 103, 100, 102), (102, 130, 101, 120)])
    tr = simulate_trade(sd, 0, 95.0, ExitConfig("2R"), NOCOST)
    cut = truncate_trade(tr, sd, int(sd.times[3]), NOCOST)
    assert cut.fills[-1].reason == "window_end" and cut.fills[-1].price == 101


def _one(sd, sig, stop):
    return Setup(np.array([sig]), np.array([stop]))


def test_risk_sizing_loses_1p5pct_at_stop():
    sd = sd_of([FLAT, FLAT, (100, 100.5, 89, 90)])
    res = run_portfolio({sd.symbol: sd}, {sd.symbol: _one(sd, 0, 90.0)}, ExitConfig("2R"),
                        risk=RiskModel(initial_capital=10_000), costs=CostModel())
    t = res.trades.iloc[0]
    assert t["pnl"] == pytest.approx(-150.0, rel=1e-9)
    assert t["r_multiple"] == pytest.approx(-1.0)
    assert res.equity.iloc[-1] == pytest.approx(10_000 - 150)


def test_position_capped_at_40pct():
    sd = sd_of([FLAT, FLAT, FLAT])
    res = run_portfolio({sd.symbol: sd}, {sd.symbol: _one(sd, 0, 99.5)}, ExitConfig("2R"),
                        risk=RiskModel(initial_capital=10_000), costs=NOCOST)
    assert res.trades.iloc[0]["notional_frac"] == pytest.approx(0.40)
    assert res.trades.iloc[0]["cost"] == pytest.approx(4_000)


def test_no_leverage_with_many_positions():
    syms = {}
    setups = {}
    for k in "ABCD":
        sd = sd_of([FLAT, FLAT, FLAT, FLAT], sym=f"{k}USDT")
        syms[sd.symbol] = sd
        setups[sd.symbol] = _one(sd, 0, 99.5)  # each wants the 40% cap
    res = run_portfolio(syms, setups, ExitConfig("3R"), risk=RiskModel(initial_capital=10_000),
                        costs=CostModel())
    costs = res.trades["cost"].sum()
    assert costs <= 10_000 + 1e-6
    assert len(res.trades) == 3  # 40% + 40% + ~20%, the fourth gets nothing
    assert res.rejected["no_cash"] == 1


def test_one_position_per_coin():
    sd = sd_of([FLAT] * 6)
    setup = Setup(np.array([0, 1, 2]), np.array([95.0, 95.0, 95.0]))
    res = run_portfolio({sd.symbol: sd}, {sd.symbol: setup}, ExitConfig("3R"), costs=NOCOST)
    assert len(res.trades) == 1 and res.rejected["busy"] == 2


def test_equity_matches_pnl_and_scale_out_value():
    sd = sd_of([FLAT, FLAT, (100, 111, 99.5, 108), (108, 116, 107, 115), FLAT])
    res = run_portfolio({sd.symbol: sd}, {sd.symbol: _one(sd, 0, 95.0)}, ExitConfig("2R_3R"),
                        risk=RiskModel(initial_capital=10_000), costs=NOCOST)
    t = res.trades.iloc[0]
    assert res.equity.iloc[-1] == pytest.approx(10_000 + t["pnl"])
    # after the 2R partial (bar 2) half the position is valued at the close of 108
    qty = t["qty"]
    expected_bar2 = 10_000 - qty * 100 + qty * 0.5 * 110 + qty * 0.5 * 108
    assert res.equity.iloc[2] == pytest.approx(expected_bar2)


def test_window_filters_entries():
    sd = sd_of([FLAT] * 10)
    setup = Setup(np.array([0, 5]), np.array([95.0, 95.0]))
    res = run_portfolio({sd.symbol: sd}, {sd.symbol: setup}, ExitConfig("3R"),
                        start=sd.index[4], end=sd.index[9], costs=NOCOST)
    assert len(res.trades) == 1
    assert res.trades.iloc[0]["exit_reason"] == "window_end"


def test_metrics():
    assert profit_factor(pd.Series([2.0, -1.0, 1.0])) == 3.0
    assert max_drawdown(pd.Series([100, 120, 90, 130])) == pytest.approx(0.25)
