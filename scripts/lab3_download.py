"""Lab 3 data: BTCUSDT/ETHUSDT spot klines 1m/5m/15m/1h/4h/1d into data/lab3/.

    python scripts/lab3_download.py
"""
import logging

import _bootstrap  # noqa: F401
from lab3.data import download

logging.basicConfig(level=logging.WARNING)
download()
