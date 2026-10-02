"""Step 1: build the top-50 universe and download daily + 4h klines (2020 -> today).

Usage:
    python scripts/download_data.py                 # full run (universe + all data)
    python scripts/download_data.py --symbols BTCUSDT ETHUSDT
    python scripts/download_data.py --update        # incremental refresh of the saved universe
"""
from __future__ import annotations

import argparse
import logging

import _bootstrap  # noqa: F401
from lab import data
from lab.config import INTERVALS, START_DATE, TOP_N
from lab.universe import exclusion_reason


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbols", nargs="*", help="explicit symbols (skip volume ranking)")
    p.add_argument("--top", type=int, default=TOP_N)
    p.add_argument("--start", default=START_DATE)
    p.add_argument("--intervals", nargs="*", default=list(INTERVALS))
    p.add_argument("--update", action="store_true", help="reuse data/universe.json, only fetch new bars")
    p.add_argument("--verify", action="store_true", help="verify .CHECKSUM files (slower)")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    dl = data.Downloader(verify_checksum=args.verify)
    if args.update:
        symbols = data.load_universe()["symbols"]
    elif args.symbols:
        bad = {s: exclusion_reason(s) for s in args.symbols if exclusion_reason(s)}
        if bad:
            raise SystemExit(f"excluded symbols: {bad}")
        symbols = args.symbols
        data.save_universe(symbols, data.rank_by_quote_volume(symbols, dl).reindex(symbols).fillna(0))
    else:
        print("listing USDT spot pairs on data.binance.vision ...")
        all_syms = dl.list_symbols()
        candidates = [s for s in all_syms if exclusion_reason(s) is None]
        print(f"{len(all_syms)} USDT pairs, {len(candidates)} after exclusions; ranking by last-month volume ...")
        vols = data.rank_by_quote_volume(candidates, dl)
        symbols = data.select_universe(all_syms, vols, args.top)
        data.save_universe(symbols, vols)
        print("universe:", ", ".join(symbols))

    for i, sym in enumerate(symbols, 1):
        for tf in args.intervals:
            df = data.update_symbol(sym, tf, dl, start=args.start)
            span = f"{df.index[0]:%Y-%m-%d} -> {df.index[-1]:%Y-%m-%d}" if len(df) else "no data"
            print(f"[{i:2d}/{len(symbols)}] {sym:<12} {tf:<3} {len(df):6d} bars  {span}")


if __name__ == "__main__":
    main()
