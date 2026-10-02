"""Step 1: download daily + 4h klines and build the point-in-time universe.

    python scripts/download_data.py            # full run
    python scripts/download_data.py --update   # incremental refresh (same symbol set)
    python scripts/download_data.py --symbols BTCUSDT ETHUSDT   # fixed list, no ranking

Full run:
  1. list every USDT spot pair in the archive (including delisted ones) and print the exclusions
  2. download 1d klines for every eligible pair (needed to rank volume at any past date)
  3. rank the top 50 by prior-3-month USDT volume at every month start since 2020 (point-in-time)
  4. download 4h klines for every coin that was ever in one of those top-50 lists
"""
from __future__ import annotations

import argparse
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pandas as pd

import _bootstrap  # noqa: F401
from lab import data
from lab.config import DOWNLOAD_START, INTERVALS, PIT_LOOKBACK_MONTHS, START_DATE, TOP_N
from lab.pit import PointInTimeUniverse
from lab.universe import excluded_by_reason, exclusion_reason


def fetch_all(symbols, interval, dl, start, workers):
    def one(sym):
        try:
            df = data.update_symbol(sym, interval, dl, start=start, workers=4)
            return sym, len(df), (f"{df.index[0]:%Y-%m-%d}..{df.index[-1]:%Y-%m-%d}" if len(df) else "no data")
        except Exception as e:  # keep going, report at the end
            return sym, -1, str(e)

    out = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, (sym, n, span) in enumerate(ex.map(one, symbols), 1):
            out[sym] = n
            if n < 0 or i % 25 == 0 or i == len(symbols):
                print(f"  [{i}/{len(symbols)}] {interval} {sym}: {'ERROR ' if n < 0 else ''}{span}")
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbols", nargs="*", help="explicit symbols (no point-in-time ranking)")
    p.add_argument("--top", type=int, default=TOP_N)
    p.add_argument("--start", default=DOWNLOAD_START)
    p.add_argument("--update", action="store_true", help="refresh the symbols in data/universe.json")
    p.add_argument("--verify", action="store_true", help="verify .CHECKSUM files (slower)")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--skip-1d", action="store_true", help="use the cached 1d files as they are (no re-download)")
    args = p.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    dl = data.Downloader(verify_checksum=args.verify)

    if args.symbols:
        bad = {s: exclusion_reason(s) for s in args.symbols if exclusion_reason(s)}
        if bad:
            raise SystemExit(f"excluded symbols: {bad}")
        for tf in INTERVALS:
            fetch_all(args.symbols, tf, dl, args.start, args.workers)
        data.save_universe(args.symbols, pd.Series(dtype=float))
        return

    if args.update:
        uni = data.load_universe()
        all_syms = uni.get("candidates", uni["symbols"])
        print(f"updating 1d for {len(all_syms)} candidates ...")
    else:
        print("listing USDT spot pairs (incl. delisted) ...")
        listed = dl.list_symbols()
        groups = excluded_by_reason(listed)
        n_ex = sum(len(v) for v in groups.values())
        print(f"{len(listed)} USDT pairs, {n_ex} excluded:")
        for reason, syms in groups.items():
            print(f"  - {reason} ({len(syms)}): {', '.join(syms)}")
        all_syms = [s for s in listed if exclusion_reason(s) is None]
        print(f"{len(all_syms)} eligible -> downloading 1d klines from {args.start} ...")
        excluded = groups

    if args.skip_1d:
        candidates = sorted(s for s in all_syms if data.cache_path(s, "1d").exists())
    else:
        got = fetch_all(all_syms, "1d", dl, args.start, args.workers)
        candidates = sorted(s for s, n in got.items() if n > 0)

    pit = PointInTimeUniverse.from_cache(candidates, top_n=args.top, lookback_months=PIT_LOOKBACK_MONTHS)
    now = pd.Timestamp.now(tz="UTC").normalize()
    monthly = pit.monthly(START_DATE, now)
    current = pit(now)
    union = sorted(set().union(*monthly.values(), current))
    print(f"point-in-time top {args.top}: {len(monthly)} monthly snapshots, {len(union)} distinct coins over time")
    print("current universe:", ", ".join(current))
    gone = sorted(set(union) - set(current))
    print(f"coins that were top-{args.top} at some point but are not today ({len(gone)}): {', '.join(gone)}")

    bases = sorted({data.base_symbol(s) for s in union})  # redenomination segments share one file
    print(f"downloading 4h klines for {len(bases)} coins ...")
    fetch_all(bases, "4h", dl, args.start, args.workers)

    prev = data.load_universe() if args.update else {}
    payload = {
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "binance",
        "symbols": current,
        "top_n": args.top,
        "lookback_months": PIT_LOOKBACK_MONTHS,
        "candidates": candidates,
        "ever_in_universe": union,
        "pit_monthly": monthly,
        "excluded": excluded if not args.update else prev.get("excluded", {}),
    }
    data.universe_path().parent.mkdir(parents=True, exist_ok=True)
    data.universe_path().write_text(json.dumps(payload, indent=1))
    print(f"saved {data.universe_path()}")


if __name__ == "__main__":
    main()
