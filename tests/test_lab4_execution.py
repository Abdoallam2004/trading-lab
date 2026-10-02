import numpy as np
import pandas as pd
import pytest

from lab3.engine import Bars
from lab4.execution import C0, C1, C2, Exec, Signal, simulate


def bars(rows):
    idx = pd.date_range("2022-01-01", periods=len(rows), freq="1h", tz="UTC")
    return Bars(pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx, dtype=float))


FLAT = (100, 100.5, 99.5, 100)


def sig(**kw):
    base = dict(sig_idx=0, valid_from=1, valid_to=3, anchor=100.0, ref_low=95.0, atr=2.0, target_r=2.0)
    base.update(kw)
    return Signal(**base)


def test_trade_through_vs_touch():
    # low touches 100 exactly but never trades 0.02% below it
    b = bars([FLAT, (100.5, 101, 100.0, 100.5), (100.5, 101, 100.0, 100.5), (100.5, 101, 100.0, 100.5)] + [FLAT] * 3)
    ex = Exec("E1", "X1", "S-b")
    assert len(simulate(b, [sig()], ex, C1, fill="through")) == 0
    assert len(simulate(b, [sig()], ex, C1, fill="touch")) == 1


def test_limit_window_expires_without_fill():
    b = bars([FLAT] + [(101, 102, 100.5, 101.5)] * 6)
    assert len(simulate(b, [sig()], Exec(), C1)) == 0


def test_ladder_partial_fill_risks_less_than_one_r():
    # E3 levels 100, 99.5, 99.0 (ATR 2); only the first fills, then the stop (95 - 1 = 94) is hit
    b = bars([FLAT, (100, 100.2, 99.9, 100), (100, 100.2, 99.8, 100), (100, 100.2, 99.8, 100), (99, 99, 93, 93.5)])
    t = simulate(b, [sig()], Exec("E3", "X1", "S-b"), C1, fill="through")
    assert len(t) == 1 and t.iloc[0]["fills"] == 1
    assert -0.5 < t.iloc[0]["r"] < -0.2          # one third of the planned size was at risk


def test_full_stop_loses_about_1r_and_c2_slips_more():
    rows = [FLAT, (100, 100.2, 99.0, 99.5), (99.5, 99.6, 93.0, 93.5)]
    b = bars(rows)
    t1 = simulate(b, [sig()], Exec("E1", "X1", "S-b"), C1)
    t2 = simulate(b, [sig()], Exec("E1", "X1", "S-b"), C2)
    assert t1.iloc[0]["r"] == pytest.approx(-1.0, abs=0.01)
    assert t2.iloc[0]["r"] < t1.iloc[0]["r"]
    assert t1.iloc[0]["ret"] == pytest.approx(-0.015, rel=0.02)   # 1.5% of equity


def test_thirds_and_breakeven():
    # entry 100, stop 94 (S-b), R = 6 -> targets 106, 112, 118
    rows = [FLAT, (100, 100.2, 99.9, 100), (100, 107, 99.9, 106.5), (106.5, 106.6, 99.0, 99.5)]
    b = bars(rows)
    x2 = simulate(b, [sig()], Exec("E1", "X2", "S-b"), C1).iloc[0]
    x3 = simulate(b, [sig()], Exec("E1", "X3", "S-b"), C1).iloc[0]
    assert x3["reason"] == "breakeven" and x3["r"] > x2["r"]


def test_c0_costs_more_than_c1():
    rows = [FLAT, (100, 100.2, 99.9, 100), (100, 113, 99.9, 112.5)]
    b = bars(rows)
    r0 = simulate(b, [sig()], Exec("E1", "X1", "S-b"), C0).iloc[0]["r"]
    r1 = simulate(b, [sig()], Exec("E1", "X1", "S-b"), C1).iloc[0]["r"]
    assert r1 > r0 > 1.8


def test_max_three_entries_per_day_and_one_position():
    rows = [FLAT] + [(100, 100.5, 99.9, 100)] * 30
    b = bars(rows)
    sigs = [sig(sig_idx=i, valid_from=i + 1, valid_to=i + 1, ref_low=99.0, target_r=0.01) for i in range(20)]
    t = simulate(b, sigs, Exec("E1", "X1", "S-a"), C1, fill="touch")
    assert len(t) <= 3
    assert (t["entry_idx"].diff().dropna() > 0).all()
