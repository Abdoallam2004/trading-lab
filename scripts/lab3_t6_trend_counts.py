"""Diagnostic (development data only): how many trades T6 takes WITH the trend filter, per
parameter set, in total and in its best 12-month train window. Explains why the walk-forward
(which needs >= 30 train trades) never traded it. Writes reports/lab3_t6_trend_counts.csv."""
import pandas as pd

import _bootstrap  # noqa: F401
from lab.config import REPORTS_DIR
from lab3.market import Market
from lab3.setups import T6BaseCrack
from lab3.wf import DEV_TESTS, Lab

lab = Lab(Market())
rows = []
for p in T6BaseCrack.grid():
    t = lab.trades(T6BaseCrack, "BTCUSDT", p, ["trend"])
    best = max(((t["entry_time"] >= ts - pd.DateOffset(months=12)) & (t["entry_time"] < ts)).sum() for ts in DEV_TESTS)
    rows.append({**p, "trades_2019_2025": len(t), "max_trades_in_a_train_window": int(best),
                 "expectancy_all": float(t["r"].mean()) if len(t) else None})
df = pd.DataFrame(rows)
df.to_csv(REPORTS_DIR / "lab3_t6_trend_counts.csv", index=False)
print(df.to_string(index=False))
