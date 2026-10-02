"""Steps 2-5: run the walk-forward backtest and write the report.

Usage:
    python scripts/run_backtest.py
    python scripts/run_backtest.py --timeframes 1d --strategies PULLBACK BREAKOUT
    python scripts/run_backtest.py --train-months 24 --test-months 6

Writes (in reports/):
    backtest_report.md        ranking + overfitting flags + per coin / per year / per regime
    passed_strategies.json    strategies that passed out-of-sample (read by scripts/scan.py)
    oos_trades.csv            every out-of-sample trade
(with a _synthetic suffix when the data is synthetic, so it can never feed the real scanner)
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import _bootstrap  # noqa: F401
from lab import data
from lab.config import DATA_DIR, PIT_LOOKBACK_MONTHS, REPORTS_DIR, START_DATE, CostModel, RiskModel
from lab.pit import PointInTimeUniverse
from lab.report import build_markdown, passed_payload
from lab.strategies import STRATEGIES
from lab.walkforward import Criteria, Market, make_windows, walk_forward, yearly_periods


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data-dir", type=Path, default=DATA_DIR)
    p.add_argument("--out", type=Path, default=REPORTS_DIR)
    p.add_argument("--timeframes", nargs="*", default=["1d", "4h"])
    p.add_argument("--strategies", nargs="*", default=list(STRATEGIES))
    p.add_argument("--train-months", type=int, default=24)
    p.add_argument("--test-months", type=int, default=12)
    p.add_argument("--capital", type=float, default=10_000)
    args = p.parse_args()

    uni = data.load_universe(args.data_dir)
    t0 = time.time()
    universe_at, pit_used = None, {}
    if uni.get("candidates"):
        # point-in-time universe: re-ranked at the start of every train/test period
        pit = PointInTimeUniverse.from_cache(uni["candidates"], args.data_dir, top_n=uni.get("top_n", 50),
                                             lookback_months=uni.get("lookback_months", PIT_LOOKBACK_MONTHS))
        end = data.load("BTCUSDT", "1d", args.data_dir).index[-1]
        start = pd.Timestamp(START_DATE, tz="UTC")
        dates = set()
        for w in make_windows(start, end, args.train_months, args.test_months):
            dates |= {w.train_start, w.test_start}
        dates |= {a for a, _ in yearly_periods(start, end)}
        dates.add(end - pd.DateOffset(months=args.train_months))
        pit_used = {f"{d:%Y-%m-%d}": pit(d) for d in sorted(dates)}
        symbols = sorted(set().union(*pit_used.values()))
        universe_at = pit
        print(f"point-in-time universe: {len(pit_used)} snapshots, {len(symbols)} distinct coins")
    else:
        symbols = uni["symbols"]
    print(f"loading {len(symbols)} coins ({uni.get('source')}) ...")
    market = Market.from_cache(symbols, args.timeframes, args.data_dir)
    if "BTCUSDT" not in market.ind.get("1d", {}):
        print("note: BTCUSDT 1d is not cached -> regime split unavailable "
              "(python scripts/download_data.py --symbols BTCUSDT --intervals 1d)")
    risk, costs, criteria = RiskModel(initial_capital=args.capital), CostModel(), Criteria()
    results = walk_forward(market, args.strategies, args.timeframes, risk=risk, costs=costs, criteria=criteria,
                           train_months=args.train_months, test_months=args.test_months,
                           universe_at=universe_at, data_start=START_DATE if universe_at else None)
    print(f"done in {time.time() - t0:.0f}s")

    meta = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "data_source": uni.get("source", "binance"), "symbols": symbols,
        "current_universe": uni.get("symbols", []), "pit": pit_used, "excluded": uni.get("excluded", {}),
        "lookback_months": uni.get("lookback_months", PIT_LOOKBACK_MONTHS), "top_n": uni.get("top_n", 50),
        "data_start": START_DATE if universe_at else f"{market.start:%Y-%m-%d}", "data_end": f"{market.end:%Y-%m-%d}",
        "timeframes": args.timeframes, "fee": costs.fee_rate, "slippage": costs.slippage,
        "risk": risk.risk_per_trade, "max_pos": risk.max_position_frac,
        "train_months": args.train_months, "test_months": args.test_months,
    }
    sfx = "_synthetic" if meta["data_source"] == "synthetic" else ""
    args.out.mkdir(parents=True, exist_ok=True)
    report = args.out / f"backtest_report{sfx}.md"
    report.write_text(build_markdown(results, meta, criteria))
    passed = passed_payload(results, meta)
    (args.out / f"passed_strategies{sfx}.json").write_text(json.dumps(passed, indent=2, default=str))
    trades = [r.oos_trades.assign(strategy=r.strategy) for r in results if len(r.oos_trades)]
    if trades:
        pd.concat(trades).to_csv(args.out / f"oos_trades{sfx}.csv", index=False)

    for r in results:
        o = r.oos
        print(f"{r.strategy:<9} {r.verdict}  trades={o.get('trades')}  PF={o.get('profit_factor', float('nan')):.2f}  "
              f"exp={o.get('expectancy_r', float('nan')):+.3f}R  maxDD={o.get('max_drawdown', float('nan')):.1%}  "
              f"flags={len(r.flags)}")
    print(f"report: {report}")
    print(f"passed out-of-sample: {[s['strategy'] for s in passed['strategies']] or 'none'}")


if __name__ == "__main__":
    main()
