import json

import numpy as np
import pandas as pd
import pytest

from lab.config import CostModel, RiskModel
from lab.engine import ExitConfig
from lab.report import build_markdown, passed_payload
from lab.scanner import scan, size_position, to_markdown
from lab.strategies import SPEC_PARAMS, StrategyConfig
from lab.synthetic import synth_4h, to_daily
from lab.walkforward import Market, walk_forward

META = {"data_source": "synthetic", "symbols": ["BTCUSDT", "ETHUSDT"], "data_start": "2020-01-01",
        "data_end": "2023-06-30", "timeframes": ["1d"], "fee": 0.001, "slippage": 0.0005, "risk": 0.015,
        "max_pos": 0.4, "train_months": 24, "test_months": 6, "generated": "test"}


@pytest.fixture(scope="module")
def results():
    frames = {"1d": {s: to_daily(synth_4h(s, "2020-01-01", "2023-07-01", seed=k))
                     for k, s in enumerate(["BTCUSDT", "ETHUSDT"])}}
    return walk_forward(Market(frames), strategies=["PULLBACK", "BREAKOUT"], timeframes=["1d"],
                        train_months=24, test_months=6, progress=lambda s: None)


def test_report_contains_required_sections(results):
    md = build_markdown(results, META)
    assert "SYNTHETIC DATA" in md
    for needle in ["Ranking by out-of-sample", "Win rate", "Profit factor", "Expectancy", "Max DD",
                   "By market regime", "By year", "By coin", "Survivorship bias", "overfitting"]:
        assert needle in md
    # every table row has the same number of cells as its header
    for block in md.split("\n\n"):
        lines = [l for l in block.splitlines() if l.startswith("|")]
        if lines:
            assert len({l.count("|") for l in lines}) == 1, block


def test_passed_payload_only_has_passes(results):
    payload = passed_payload(results, META)
    names = {r.strategy for r in results if r.verdict == "PASS"}
    assert {s["strategy"] for s in payload["strategies"]} == names
    json.dumps(payload)  # serialisable
    for s in payload["strategies"]:
        StrategyConfig.from_dict(s["config"])


def test_size_position_risk_and_cap():
    risk, costs = RiskModel(), CostModel(0.0, 0.0)
    qty, notional = size_position(10_000, 100.0, 90.0, risk, costs)
    assert qty * 10 == pytest.approx(150)          # 1.5% risk
    qty, notional = size_position(10_000, 100.0, 99.9, risk, costs)
    assert notional == pytest.approx(4_000)         # 40% cap


def _breakout_frame(n=300):
    idx = pd.date_range("2025-01-01", periods=n, freq="1D", tz="UTC")
    close = 100 + np.sin(np.arange(n) / 5)
    close[-1] = 110  # breakout on the last closed bar
    vol = np.full(n, 1000.0); vol[-1] = 5000
    op = np.r_[close[0], close[:-1]]
    return pd.DataFrame({"open": op, "high": np.maximum(op, close) + 0.5, "low": np.minimum(op, close) - 0.5,
                         "close": close, "volume": vol, "quote_volume": vol, "trades": 1.0}, index=idx)


def test_scanner_only_uses_passed_strategies_and_skips_unclosed_bar():
    df = _breakout_frame()
    cfg = StrategyConfig.make("BREAKOUT", "1d", SPEC_PARAMS["BREAKOUT"], ExitConfig("2R_3R"))
    passed = {"strategies": [{"strategy": "BREAKOUT", "config": cfg.to_dict(), "oos_by_regime": {}}]}
    now = df.index[-1] + pd.Timedelta(days=1, hours=1)   # last bar closed
    sig, warn = scan(passed, {"1d": {"ABCUSDT": df}}, None, 10_000, now=now)
    assert list(sig["symbol"]) == ["ABCUSDT"] and warn == []
    row = sig.iloc[0]
    assert row["stop"] < row["entry_ref"] < row["target_2R"] < row["target_3R"]
    # same data, but the last bar has not closed yet -> it must be ignored
    sig2, _ = scan(passed, {"1d": {"ABCUSDT": df}}, None, 10_000, now=df.index[-1] + pd.Timedelta(hours=5))
    assert len(sig2) == 0
    # nothing passed -> nothing scanned
    sig3, _ = scan({"strategies": []}, {"1d": {"ABCUSDT": df}}, None, 10_000, now=now)
    assert len(sig3) == 0
    md = to_markdown(sig, warn, passed, 10_000, now)
    assert "ABCUSDT" in md and "no leverage" in md


def test_scanner_warns_on_stale_data():
    df = _breakout_frame()
    cfg = StrategyConfig.make("BREAKOUT", "1d", SPEC_PARAMS["BREAKOUT"])
    passed = {"strategies": [{"strategy": "BREAKOUT", "config": cfg.to_dict()}]}
    sig, warn = scan(passed, {"1d": {"ABCUSDT": df}}, None, 10_000, now=df.index[-1] + pd.Timedelta(days=10))
    assert len(sig) == 0 and "stale" in warn[0]


def test_regime_filter_skips_losing_regime(ohlcv):
    df = _breakout_frame()
    btc = ohlcv(np.linspace(100, 300, 300), start="2025-01-01")  # uptrend -> BTC>200D
    cfg = StrategyConfig.make("BREAKOUT", "1d", SPEC_PARAMS["BREAKOUT"])
    passed = {"strategies": [{"strategy": "BREAKOUT", "config": cfg.to_dict(),
                              "oos_by_regime": {"BTC>200D": {"trades": 40, "expectancy_r": -0.2}}}]}
    now = df.index[-1] + pd.Timedelta(days=1, hours=1)
    sig, warn = scan(passed, {"1d": {"ABCUSDT": df}}, btc, 10_000, now=now, regime_filter=True)
    assert len(sig) == 0 and "skipped" in warn[0]
    sig, _ = scan(passed, {"1d": {"ABCUSDT": df}}, btc, 10_000, now=now, regime_filter=False)
    assert len(sig) == 1 and sig.iloc[0]["oos_exp_in_regime"] == -0.2
