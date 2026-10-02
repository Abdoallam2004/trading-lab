import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def make_ohlcv(closes, start="2021-01-01", freq="1D", spread=0.01, volume=1000.0):
    closes = np.asarray(closes, dtype=float)
    opens = np.r_[closes[0], closes[:-1]]
    high = np.maximum(opens, closes) * (1 + spread)
    low = np.minimum(opens, closes) * (1 - spread)
    idx = pd.date_range(start, periods=len(closes), freq=freq, tz="UTC", name="open_time")
    vol = np.full(len(closes), volume) if np.isscalar(volume) else np.asarray(volume, float)
    return pd.DataFrame({"open": opens, "high": high, "low": low, "close": closes,
                         "volume": vol, "quote_volume": vol * closes, "trades": 100.0}, index=idx)


@pytest.fixture
def ohlcv():
    return make_ohlcv
