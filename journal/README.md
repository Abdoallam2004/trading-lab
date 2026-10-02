# Trading journal (Lab 4 phase F-2)

Purpose: find out whether **your own judgment** has an edge, after 50–100 paper trades,
using the same yardsticks as the labs (expectancy in R, profit factor, losing streaks).

1. Copy `trades_template.csv` to `trades.csv` and add one row per closed trade.
2. Run `python scripts/journal_stats.py` (or `--file path/to/trades.csv`).

## Columns

| column | meaning |
|---|---|
| trade_id | any unique id |
| opened_utc, closed_utc | ISO time, UTC (e.g. 2026-10-05T14:30) |
| pair | BTCUSDT / ETHUSDT (spot only) |
| setup | your name for the idea (e.g. "range reclaim", "funding flush") — stats are grouped by it |
| regime | market state you saw at entry, e.g. "BTC>200D" / "BTC<200D" — stats are grouped by it |
| thesis | one sentence: why this trade |
| funding, open_interest, fear_greed, macro | what you saw (free text or numbers) |
| levels | key levels you used |
| entry_prices | your planned ladder, `;`-separated (e.g. `61000;60945;60890`) |
| entry_fills | actual fills `qty@price;qty@price` |
| stop | stop price |
| targets | `;`-separated |
| exit_fills | actual exits `qty@price;qty@price` |
| fees_usdt | total fees paid (BNB discount included) |
| planned_risk_usdt | what you would lose at the stop with the full ladder filled (1.5% of equity) |
| result_r | optional — if empty it is computed as (exit value − entry value − fees) ÷ planned_risk_usdt |
| followed_plan | yes / no |
| emotion | 1 (calm) … 5 (stressed, FOMO, revenge) |
| notes | anything else |

Rules of the game: decide the stop and the risk **before** entering; log every trade, especially the bad ones;
do not judge the method before 50 trades.
