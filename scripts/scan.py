"""Daily scanner: only uses strategies listed in reports/passed_strategies.json.

Usage:
    python scripts/scan.py --equity 5000             # scan cached data
    python scripts/scan.py --equity 5000 --update    # refresh cache from data.binance.vision first (D-1 data)
    python scripts/scan.py --equity 5000 --live      # top up with the latest closed bars from api.binance.com
    python scripts/scan.py --regime-filter           # skip strategies with negative OOS expectancy in today's regime
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

import _bootstrap  # noqa: F401
from lab import data
from lab.config import DATA_DIR, REPORTS_DIR
from lab.scanner import scan, to_markdown


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--equity", type=float, default=10_000, help="account size in USDT for position sizing")
    p.add_argument("--passed", type=Path, default=REPORTS_DIR / "passed_strategies.json")
    p.add_argument("--data-dir", type=Path, default=DATA_DIR)
    p.add_argument("--update", action="store_true")
    p.add_argument("--live", action="store_true")
    p.add_argument("--regime-filter", action="store_true")
    p.add_argument("--out", type=Path, default=REPORTS_DIR)
    args = p.parse_args()

    if not args.passed.exists():
        raise SystemExit(f"{args.passed} not found: run scripts/run_backtest.py first")
    passed = json.loads(args.passed.read_text())
    if not passed.get("strategies"):
        print("No strategy passed out-of-sample validation -> nothing to scan. (This is a valid result.)")
        return
    symbols = data.load_universe(args.data_dir)["symbols"]
    tfs = sorted({s["config"]["timeframe"] for s in passed["strategies"]} | {"1d"})
    dl = data.Downloader() if args.update else None
    frames = {tf: {} for tf in tfs}
    for tf in tfs:
        for sym in sorted(set(symbols) | {"BTCUSDT"}):
            try:
                df = data.update_symbol(sym, tf, dl, data_dir=args.data_dir) if dl else data.load(sym, tf, args.data_dir)
                if args.live:
                    df = data.merge_frames([df, data.fetch_recent_api(sym, tf)])
            except FileNotFoundError:
                continue
            frames[tf][sym] = df
    btc = frames["1d"].get("BTCUSDT")
    now = pd.Timestamp.now(tz="UTC")
    # BTC only feeds the regime unless it is in the universe
    frames = {tf: {s: d for s, d in f.items() if s in symbols} for tf, f in frames.items()}
    signals, warnings = scan(passed, frames, btc, args.equity, now=now, regime_filter=args.regime_filter)
    md = to_markdown(signals, warnings, passed, args.equity, now)
    print(md)
    args.out.mkdir(parents=True, exist_ok=True)
    out = args.out / f"scan_{now:%Y-%m-%d}.md"
    out.write_text(md)
    print(f"saved {out}")


if __name__ == "__main__":
    main()
