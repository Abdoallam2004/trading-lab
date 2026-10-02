import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_logger_parsers():
    lg = load_script("daily_logger")
    p = lg.parse_premium({"markPrice": "101", "indexPrice": "100", "lastFundingRate": "0.0001"})
    assert p["premium"] == pytest.approx(0.01) and p["last_funding_rate"] == 0.0001
    k = [[0, "1", "1", "1", "1", "1", 0, "100", 1, "1", "60", "0"], [1, "2", "2", "2", "2", "2", 0, "999", 1, "1", "1", "0"]]
    s = lg.parse_spot_kline(k)
    assert s["taker_delta"] == pytest.approx(20.0)        # uses the last CLOSED day, not the running one
    f = lg.parse_fng({"data": [{"value": "17", "value_classification": "Extreme Fear", "timestamp": "1700000000"}]})
    assert f["fear_greed"] == 17


def test_logger_rule_states_and_idempotent_append(tmp_path):
    lg = load_script("daily_logger")
    weekly = [100.0] * 199 + [150.0]
    frozen = {"accumulation": [{"id": "S2-aggressive", "table": [[1.5, 3.0], [2.5, 1.0], [3.5, 0.25], [1e9, 0.0]],
                                "trim_at": 3.5}, {"id": "S1-20w"}]}
    st = lg.rule_states(weekly, frozen)
    assert st[0]["action"] == "weekly buy x3.0" and st[1]["signal"] == "up"
    p = tmp_path / "x.csv"
    lg.append(p, {"date": "2026-10-05", "asset": "BTCUSDT", "v": 1})
    lg.append(p, {"date": "2026-10-05", "asset": "BTCUSDT", "v": 2})
    lg.append(p, {"date": "2026-10-06", "asset": "BTCUSDT", "v": 3})
    df = pd.read_csv(p)
    assert len(df) == 2 and df.iloc[0]["v"] == 2


def test_logger_survives_network_errors():
    lg = load_script("daily_logger")

    class Down:
        def get(self, *a, **k):
            raise ConnectionError("blocked")
    market, rules = lg.collect(session=Down())
    assert len(market) == 2 and "premium_error" in market[0] and rules[0]["signal"] == "error"


def test_journal_stats(tmp_path):
    js = load_script("journal_stats")
    rows = [
        {"trade_id": 1, "opened_utc": "2026-10-01T10:00", "closed_utc": "2026-10-02T10:00", "pair": "BTCUSDT",
         "setup": "A", "regime": "BTC>200D", "entry_fills": "0.01@60000", "exit_fills": "0.01@61200",
         "fees_usdt": 0.9, "planned_risk_usdt": 15, "result_r": None, "followed_plan": "yes", "emotion": 2},
        {"trade_id": 2, "opened_utc": "2026-10-03T10:00", "closed_utc": "2026-10-04T10:00", "pair": "BTCUSDT",
         "setup": "A", "regime": "BTC>200D", "entry_fills": "0.01@60000", "exit_fills": "0.01@58500",
         "fees_usdt": 0.9, "planned_risk_usdt": 15, "result_r": None, "followed_plan": "no", "emotion": 4},
        {"trade_id": 3, "opened_utc": "2026-10-05T10:00", "closed_utc": "2026-10-06T10:00", "pair": "ETHUSDT",
         "setup": "B", "regime": "BTC>200D", "entry_fills": "", "exit_fills": "", "fees_usdt": 0,
         "planned_risk_usdt": 15, "result_r": -0.5, "followed_plan": "yes", "emotion": 1},
    ]
    p = tmp_path / "t.csv"
    pd.DataFrame(rows).to_csv(p, index=False)
    df = js.load(p)
    assert df["r"].tolist() == pytest.approx([(12 - 0.9) / 15, (-15 - 0.9) / 15, -0.5])
    s = js.stats(df["r"])
    assert s["trades"] == 3 and s["longest_losing_streak"] == 2
    assert "too few" in js.report(df)
