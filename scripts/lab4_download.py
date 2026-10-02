"""Lab 4 data download (Binance spot + USD-M futures archives, VIX, 10y monthly).

    python scripts/lab4_download.py
"""
import logging

import _bootstrap  # noqa: F401
from lab4.data import download_all

logging.basicConfig(level=logging.WARNING)
download_all()
