import numpy as np
import pandas as pd
import pytest

from lab.regime import BEAR, BULL, UNKNOWN, btc_regime, regime_at
from lab.synthetic import synth_4h, to_daily
from lab.walkforward import Criteria, Market, StrategyWF, judge, make_windows, walk_forward


def test_windows_are_sequential_and_unseen():
    ws = make_windows("2020-01-01", "2026-10-01", train_months=24, test_months=12)
    assert ws[0].train_start == pd.Timestamp("2020-01-01") and ws[0].test_start == pd.Timestamp("2022-01-01")
    for a, b in zip(ws, ws[1:]):
        assert a.test_end == b.test_start            # OOS periods tile the timeline
    for w in ws:
        assert w.train_end <= w.test_start           # test never overlaps its train
    assert ws[-1].test_end == pd.Timestamp("2026-10-01")  # partial last window kept
    assert len(ws) == 5


def test_regime_known_only_after_close(ohlcv):
    closes = np.r_[np.full(200, 100.0), [120.0, 80.0]]
    d = ohlcv(closes, start="2021-01-01")
    reg = btc_regime(d)
    day200 = d.index[200]  # first close above SMA
    assert regime_at(reg, [day200])[0] == UNKNOWN or regime_at(reg, [day200])[0] != BULL
    assert regime_at(reg, [day200 + pd.Timedelta(days=1)])[0] == BULL
    assert regime_at(reg, [day200 + pd.Timedelta(days=2)])[0] == BEAR
    assert regime_at(reg, [d.index[0]])[0] == UNKNOWN


@pytest.fixture(scope="module")
def small_market():
    frames = {"1d": {}, "4h": {}}
    for k, s in enumerate(["BTCUSDT", "ETHUSDT", "SOLUSDT"]):
        h = synth_4h(s, "2020-01-01", "2024-07-01", seed=k)
        frames["4h"][s] = h
        frames["1d"][s] = to_daily(h)
    return Market(frames)


def test_walk_forward_end_to_end(small_market):
    res = walk_forward(small_market, strategies=["PULLBACK", "BREAKOUT"], timeframes=["1d"],
                       train_months=24, test_months=12, progress=lambda s: None)
    assert {r.strategy for r in res} == {"PULLBACK", "BREAKOUT"}
    for r in res:
        assert r.verdict in ("PASS", "FAIL")
        assert len(r.windows) == 3  # 2022, 2023, partial 2024H1
        assert r.n_configs == 16
        if len(r.oos_trades):
            # every OOS trade was entered inside a TEST period, never inside the first TRAIN period
            assert (r.oos_trades["entry_time"] >= pd.Timestamp("2022-01-01", tz="UTC")).all()
            assert set(r.oos_trades["regime"]) <= {BULL, BEAR, UNKNOWN}
    # ranked: passes first
    verdicts = [r.verdict for r in res]
    assert verdicts == sorted(verdicts, key=lambda v: v != "PASS")


def _wf(oos, is_exp, windows, trades=None):
    trades = trades if trades is not None else pd.DataFrame(columns=["pnl", "symbol", "regime", "r_multiple"])
    return StrategyWF("X", 4, windows, trades, pd.Series(dtype=float), oos, {"expectancy_r": is_exp},
                      trades, pd.Series(dtype=float), {"expectancy_r": np.nan}, trades, {}, None)


def _win(exp, chosen="a", med=0.0):
    return {"test": {"trades": 20, "expectancy_r": exp}, "chosen_cfg": chosen,
            "chosen_test_exp_r": exp, "test_median_cfg_exp_r": med}


def test_judge_flags_overfitting():
    oos = {"trades": 100, "profit_factor": 1.05, "expectancy_r": 0.02, "max_drawdown": 0.2}
    wf = _wf(oos, is_exp=0.6, windows=[_win(0.1, "a"), _win(-0.1, "b"), _win(0.05, "c")])
    judge(wf, Criteria())
    assert wf.verdict == "FAIL"
    assert any(f.startswith("OVERFIT") for f in wf.flags)
    assert any(f.startswith("UNSTABLE") for f in wf.flags)


def test_judge_passes_robust_record():
    oos = {"trades": 120, "profit_factor": 1.6, "expectancy_r": 0.3, "max_drawdown": 0.18}
    wf = _wf(oos, is_exp=0.35, windows=[_win(0.3, "a", -0.1), _win(0.2, "a", 0.0), _win(0.4, "a", 0.1)])
    judge(wf, Criteria())
    assert wf.verdict == "PASS" and wf.flags == []


def test_judge_fails_on_drawdown_and_few_trades():
    oos = {"trades": 10, "profit_factor": 2.0, "expectancy_r": 0.5, "max_drawdown": 0.5}
    wf = _wf(oos, is_exp=0.5, windows=[_win(0.5)])
    judge(wf, Criteria())
    assert wf.verdict == "FAIL"
    assert any("OOS trades" in r for r in wf.reasons) and any("drawdown" in r for r in wf.reasons)
