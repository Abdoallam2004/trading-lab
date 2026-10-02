# Lab 4 — data inventory

Everything below was downloaded by `scripts/lab4_download.py` into `data/lab4/` (not committed). 'Gaps' counts intervals longer than 1.5× the nominal step (weekends/holidays for VIX and the 10y series are expected; for 24/7 crypto series they are exchange outages or archive holes).

## Available

| Dataset | Source | First | Last | Step | Rows | Gaps | Largest gap |
|---|---|---|---|---|---|---|---|
| `funding_BTCUSDT` | Binance USD-M funding rate — `data/futures/um/{monthly,daily}/fundingRate` | 2020-01-01 | 2026-09-30 | 8h | 7395 | 0 | none |
| `funding_ETHUSDT` | Binance USD-M funding rate — `data/futures/um/{monthly,daily}/fundingRate` | 2020-01-01 | 2026-09-30 | 8h | 7395 | 0 | none |
| `metrics_BTCUSDT` | Binance USD-M daily metrics (5-min open interest, top-trader & global long/short ratios, taker buy/sell volume ratio) — `data/futures/um/daily/metrics` | 2020-09-01 | 2026-10-01 | 5min | 639302 | 156 | 0 days 10:30:00 (ending 2024-02-17 00:00) |
| `metrics_ETHUSDT` | Binance USD-M daily metrics (5-min open interest, top-trader & global long/short ratios, taker buy/sell volume ratio) — `data/futures/um/daily/metrics` | 2021-12-01 | 2026-10-01 | 5min | 508468 | 10 | 0 days 10:30:00 (ending 2024-02-17 00:00) |
| `premium_BTCUSDT_1d` | Binance USD-M premium-index klines — `data/futures/um/monthly/premiumIndexKlines` | 2020-01-01 | 2026-09-30 | 1D | 2457 | 5 | 5 days 00:00:00 (ending 2021-07-28 00:00) |
| `premium_BTCUSDT_4h` | Binance USD-M premium-index klines — `data/futures/um/monthly/premiumIndexKlines` | 2020-01-01 | 2026-09-30 | 4h | 14742 | 5 | 4 days 04:00:00 (ending 2021-07-28 00:00) |
| `premium_ETHUSDT_1d` | Binance USD-M premium-index klines — `data/futures/um/monthly/premiumIndexKlines` | 2020-01-01 | 2026-09-30 | 1D | 2457 | 5 | 5 days 00:00:00 (ending 2021-07-28 00:00) |
| `premium_ETHUSDT_4h` | Binance USD-M premium-index klines — `data/futures/um/monthly/premiumIndexKlines` | 2020-01-01 | 2026-09-30 | 4h | 14742 | 5 | 4 days 04:00:00 (ending 2021-07-28 00:00) |
| `spot_BTCUSDT_1d` | Binance spot klines incl. taker-buy volume — data.binance.vision (S3 mirror) `data/spot/{monthly,daily}/klines` | 2017-08-17 | 2026-10-01 | 1D | 3333 | 0 | none |
| `spot_BTCUSDT_1h` | Binance spot klines incl. taker-buy volume — data.binance.vision (S3 mirror) `data/spot/{monthly,daily}/klines` | 2017-08-17 | 2026-10-01 | 1h | 79861 | 28 | 1 days 09:28:14.789000 (ending 2018-02-09 09:28) |
| `spot_BTCUSDT_4h` | Binance spot klines incl. taker-buy volume — data.binance.vision (S3 mirror) `data/spot/{monthly,daily}/klines` | 2017-08-17 | 2026-10-01 | 4h | 19980 | 9 | 1 days 08:00:00 (ending 2018-02-09 08:00) |
| `spot_ETHUSDT_1d` | Binance spot klines incl. taker-buy volume — data.binance.vision (S3 mirror) `data/spot/{monthly,daily}/klines` | 2017-08-17 | 2026-10-01 | 1D | 3333 | 0 | none |
| `spot_ETHUSDT_1h` | Binance spot klines incl. taker-buy volume — data.binance.vision (S3 mirror) `data/spot/{monthly,daily}/klines` | 2017-08-17 | 2026-10-01 | 1h | 79861 | 28 | 1 days 09:28:14.800000 (ending 2018-02-09 09:28) |
| `spot_ETHUSDT_4h` | Binance spot klines incl. taker-buy volume — data.binance.vision (S3 mirror) `data/spot/{monthly,daily}/klines` | 2017-08-17 | 2026-10-01 | 4h | 19980 | 9 | 1 days 08:00:00 (ending 2018-02-09 08:00) |
| `spot_EURUSDT_1d` | Binance spot klines incl. taker-buy volume — data.binance.vision (S3 mirror) `data/spot/{monthly,daily}/klines` | 2020-01-03 | 2026-10-01 | 1D | 2464 | 0 | none |
| `spot_PAXGUSDT_1d` | Binance spot klines incl. taker-buy volume — data.binance.vision (S3 mirror) `data/spot/{monthly,daily}/klines` | 2020-08-28 | 2026-10-01 | 1D | 2226 | 0 | none |
| `us10y_monthly` | US 10-year yield, MONTHLY only, via github.com/datasets/bond-yields-us-10y | 1953-04-01 | 2026-08-01 | MS | 881 | 0 | none |
| `vix` | CBOE VIX daily, via github.com/datasets/finance-vix (raw.githubusercontent.com) | 1990-01-02 | 2026-09-22 | 1D | 9278 | 1996 | 7 days 00:00:00 (ending 2001-09-17 00:00) |

Proxies used where the requested series is unavailable (labelled as proxies everywhere they are used):
- **Gold → `spot_PAXGUSDT_1d`** (Binance PAXG/USDT, a token redeemable for 1 troy oz; from 2020-08-28).
- **Dollar index (DXY) → inverse of `spot_EURUSDT_1d`** (EUR is ~57.6% of DXY; from 2020-01-03).

## Not available (skipped, never fabricated)

| Requested | Why | Effect |
|---|---|---|
| Crypto Fear & Greed history (alternative.me) | host blocked by this environment's network policy | D7 and the F&G part of L3 are skipped; the daily logger records F&G going forward where the host is reachable |
| FRED: DGS10 daily, DFF, WALCL, DTWEXBGS | fred.stlouisfed.org and api.stlouisfed.org blocked; only a MONTHLY 10y series is reachable (DataHub) | no daily 10y, Fed funds or Fed balance-sheet correlations; DXY replaced by the EUR/USDT proxy |
| Nasdaq-100 / QQQ daily | stooq, Yahoo, Alpha Vantage, FMP hosts blocked; no free mirror reachable | no Nasdaq correlation or Nasdaq-based macro regime; the macro regime uses VIX and the dollar proxy instead |
| Gold spot daily (LBMA) | no reachable daily source (DataHub has monthly only) | PAXG/USDT proxy |
| FOMC meeting dates, US CPI release dates | federalreserve.gov and bls.gov blocked | D-3 event windows and the D-4 calendar filter are skipped (typing the dates from memory would risk fabricated data) |
| US spot BTC ETF daily net flows | farside.co.uk blocked; no other free source with clear terms | skipped |
| Liquidation history | Binance's `liquidationSnapshot` archive is empty for BTCUSDT/ETHUSDT; the live force-order endpoint needs an API key | liquidations are proxied by open-interest drops (D3); S-c stops (below liquidation clusters) cannot be tested |
| Token-unlock history | no free historical source | L4 skipped; see Phase F |

## How the user can unblock the missing sources
Allow these hosts in the environment's network settings and re-run `scripts/lab4_download.py` (and extend it): `api.alternative.me`, `fred.stlouisfed.org`, `stooq.com`, `www.federalreserve.gov`, `www.bls.gov`, `fapi.binance.com` (live futures endpoints for the logger).
