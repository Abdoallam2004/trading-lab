"""Lab 2 data: extend daily klines back to 2017-08 (all eligible USDT pairs, incl. delisted)
and fetch the free CoinMetrics BTC file. Requires Lab 1's data (scripts/download_data.py).

    python scripts/lab2_download.py
"""
import logging

import _bootstrap  # noqa: F401
from lab import data as lab1
from lab.universe import exclusion_reason
from lab2 import data as d2


def main():
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    dl = lab1.Downloader()
    print("CoinMetrics:", d2.download_coinmetrics())
    syms = [s for s in dl.list_symbols() if exclusion_reason(s) is None]
    print(f"{len(syms)} eligible USDT pairs -> daily klines 2017-08..2019-09 into {d2.EARLY_DIR}")
    got = d2.download_early(syms, dl)
    print(f"done: {sum(n > 0 for n in got.values())} pairs had data before 2019-10")


if __name__ == "__main__":
    main()
