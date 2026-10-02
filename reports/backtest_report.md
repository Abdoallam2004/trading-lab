# Halal Spot Crypto Backtest Report

Generated 2026-10-02T01:04+00:00  
Data: binance · 2020-01-01 → 2026-09-30 · point-in-time top 50 (re-ranked by prior 3-month volume at the start of every period; 175 distinct coins over time) · timeframes 1d, 4h  
Rules: spot only, long only, no leverage, no shorting · fees 0.10%/side + slippage 0.05%/fill · risk 1.5% of equity per trade · max 40% of equity per coin · one position per coin  
Walk-forward: optimise on 24 months, test on the next 12 unseen months, roll forward. Pass bar (OOS): ≥30 trades, PF ≥ 1.15, expectancy ≥ 0.05R, max DD ≤ 35%, positive in ≥ 50% of OOS windows.

## 1. Ranking by out-of-sample results

| # | Strategy | Verdict | OOS trades | Win rate | Profit factor | Expectancy | Exp. $/trade | Max DD | OOS return | In-sample exp. | Overfit flags |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **PULLBACK** | ❌ FAIL | 610 | 26.1% | 0.71 | -0.054R | -10$ | 78.8% | -61.3% | +0.274R | 2 |
| 2 | **BASE** | ❌ FAIL | 273 | 31.9% | 0.53 | -0.155R | -21$ | 78.1% | -58.4% | +0.522R | 3 |
| 3 | **BREAKOUT** | ❌ FAIL | 700 | 27.0% | 0.60 | -0.122R | -12$ | 87.8% | -83.8% | +0.380R | 4 |

Expectancy is the average result per trade in R (1R = the amount risked). "In-sample exp." is what the optimiser saw on its training windows; a big gap to OOS = overfitting.

### Baseline: the exact specified rules, no optimisation (same OOS periods, daily, exit 2R/3R)

| Strategy | Trades | Win rate | Profit factor | Expectancy | Max DD | Return |
|---|---|---|---|---|---|---|
| PULLBACK | 566 | 25.6% | 0.50 | -0.272R | 92.7% | -90.2% |
| BASE | 258 | 36.4% | 0.89 | +0.030R | 67.4% | -17.9% |
| BREAKOUT | 477 | 35.8% | 0.68 | -0.010R | 77.3% | -62.7% |

## 2. Verdicts and overfitting flags

### PULLBACK: FAIL

- Configs searched per window: 32 (more configs = more chances to fit noise)
- ❌ OOS profit factor 0.71 < 1.15
- ❌ OOS expectancy -0.054R < 0.05R
- ❌ OOS max drawdown 78.8% > 35%
- ❌ positive in only 2/5 OOS windows
- 🚩 OVERFIT: OOS expectancy -0.054R vs in-sample +0.274R (120% worse)
- 🚩 REGIME-DEPENDENT: works only when BTC<200D (loses when BTC>200D)
- Config for live scanning (best on the latest 24 months): `PULLBACK 4h [prox_atr=1.0 rsi_hi=55 rsi_lo=40 swing=10] exit=trail3ATR`

### BASE: FAIL

- Configs searched per window: 32 (more configs = more chances to fit noise)
- ❌ OOS profit factor 0.53 < 1.15
- ❌ OOS expectancy -0.155R < 0.05R
- ❌ OOS max drawdown 78.1% > 35%
- ❌ positive in only 2/5 OOS windows
- 🚩 OVERFIT: OOS expectancy -0.155R vs in-sample +0.522R (130% worse)
- 🚩 NO EDGE FROM OPTIMISING: the chosen config did no better OOS than the median config
- 🚩 Spec rules (no optimisation) beat the optimised version OOS (+0.030R vs -0.155R)
- Config for live scanning (best on the latest 24 months): `BASE 1d [adx_min=15 adx_rise=3 swing=10] exit=3R`

### BREAKOUT: FAIL

- Configs searched per window: 32 (more configs = more chances to fit noise)
- ❌ OOS profit factor 0.60 < 1.15
- ❌ OOS expectancy -0.122R < 0.05R
- ❌ OOS max drawdown 87.8% > 35%
- 🚩 OVERFIT: OOS expectancy -0.122R vs in-sample +0.380R (132% worse)
- 🚩 UNSTABLE: optimiser picked a different config in every window
- 🚩 NO EDGE FROM OPTIMISING: the chosen config did no better OOS than the median config
- 🚩 Spec rules (no optimisation) beat the optimised version OOS (-0.010R vs -0.122R)
- Config for live scanning (best on the latest 24 months): `BREAKOUT 1d [lookback=20 swing=10 vol_mult=2.0] exit=trail3ATR`

## 3. Details per strategy

### PULLBACK

**Walk-forward windows**

| Window | Chosen config | Train trades | Train exp. | Test trades | Test exp. | Test PF | Median config test exp. | Configs positive in test |
|---|---|---|---|---|---|---|---|---|
| train 2020-01→2022-01, test 2022-01→2023-01 | `PULLBACK 1d [prox_atr=0.5 rsi_hi=55 rsi_lo=40 swing=10] exit=trail3ATR` | 442 | +0.730R | 97 | -0.562R | 0.19 | -0.450R | 0.0% |
| train 2021-01→2023-01, test 2023-01→2024-01 | `PULLBACK 1d [prox_atr=0.5 rsi_hi=55 rsi_lo=40 swing=10] exit=trail3ATR` | 329 | +0.298R | 115 | +0.317R | 1.72 | +0.034R | 68.8% |
| train 2022-01→2024-01, test 2024-01→2025-01 | `PULLBACK 1d [prox_atr=0.5 rsi_hi=55 rsi_lo=40 swing=10] exit=trail3ATR` | 190 | +0.003R | 207 | -0.034R | 0.79 | -0.073R | 0.0% |
| train 2023-01→2025-01, test 2025-01→2026-01 | `PULLBACK 1d [prox_atr=0.5 rsi_hi=55 rsi_lo=40 swing=10] exit=trail3ATR` | 297 | +0.178R | 149 | -0.329R | 0.38 | -0.290R | 0.0% |
| train 2024-01→2026-01, test 2026-01→2026-09 | `PULLBACK 1d [prox_atr=0.5 rsi_hi=55 rsi_lo=40 swing=10] exit=trail3ATR` | 330 | -0.117R | 42 | +0.976R | 2.79 | +0.100R | 68.8% |

**By market regime (OOS)**

| Regime | Trades | Win rate | Profit factor | Expectancy | Exp. $/trade | Net P&L |
|---|---|---|---|---|---|---|
| BTC<200D | 183 | 27.3% | 0.69 | +0.142R | -14$ | -2,558$ |
| BTC>200D | 427 | 25.5% | 0.72 | -0.138R | -8$ | -3,577$ |

**By market regime (spec rules, full history)**

| Regime | Trades | Win rate | Profit factor | Expectancy | Exp. $/trade | Net P&L |
|---|---|---|---|---|---|---|
| BTC<200D | 206 | 30.1% | 0.59 | -0.170R | -93$ | -19,122$ |
| BTC>200D | 781 | 35.7% | 1.11 | +0.079R | +17$ | +13,159$ |

**By year (OOS)**

| Year | Trades | Win rate | Profit factor | Expectancy | Exp. $/trade | Net P&L |
|---|---|---|---|---|---|---|
| 2022 | 97 | 13.4% | 0.19 | -0.562R | -57$ | -5,505$ |
| 2023 | 115 | 33.0% | 1.72 | +0.317R | +16$ | +1,807$ |
| 2024 | 207 | 32.9% | 0.79 | -0.034R | -7$ | -1,525$ |
| 2025 | 149 | 18.1% | 0.38 | -0.329R | -16$ | -2,349$ |
| 2026 | 42 | 31.0% | 2.79 | +0.976R | +34$ | +1,437$ |

**By year (spec rules, full history 2020→, not walk-forward)**

| Year | Trades | Win rate | Profit factor | Expectancy | Exp. $/trade | Net P&L |
|---|---|---|---|---|---|---|
| 2020 | 162 | 46.3% | 1.72 | +0.440R | +60$ | +9,687$ |
| 2021 | 257 | 46.7% | 1.26 | +0.424R | +85$ | +21,815$ |
| 2022 | 91 | 14.3% | 0.23 | -0.637R | -262$ | -23,844$ |
| 2023 | 98 | 31.6% | 0.88 | -0.101R | -14$ | -1,362$ |
| 2024 | 191 | 29.3% | 0.68 | -0.130R | -34$ | -6,553$ |
| 2025 | 147 | 18.4% | 0.36 | -0.484R | -42$ | -6,153$ |
| 2026 | 41 | 46.3% | 1.42 | +0.245R | +11$ | +446$ |

**By coin (OOS, sorted by net P&L)**

| Coin | Trades | Win rate | Profit factor | Expectancy | Exp. $/trade | Net P&L |
|---|---|---|---|---|---|---|
| ZECUSDT | 16 | 18.8% | 2.22 | +1.827R | +48$ | +764$ |
| LINKUSDT | 12 | 16.7% | 2.76 | +0.850R | +59$ | +709$ |
| BCHUSDT | 22 | 31.8% | 1.99 | +0.208R | +22$ | +481$ |
| TRXUSDT | 39 | 41.0% | 1.59 | +0.498R | +10$ | +384$ |
| BNBUSDT | 37 | 48.6% | 1.56 | +0.378R | +9$ | +331$ |
| XRPUSDT | 16 | 31.2% | 2.00 | +0.397R | +18$ | +289$ |
| APTUSDT | 9 | 44.4% | 2.14 | +0.502R | +29$ | +265$ |
| AXSUSDT | 1 | 100.0% | inf | +2.789R | +240$ | +240$ |
| ARUSDT | 2 | 50.0% | 30.82 | +0.933R | +76$ | +152$ |
| NEARUSDT | 16 | 31.2% | 1.22 | +0.286R | +9$ | +138$ |
| BTCUSDT | 49 | 30.6% | 1.09 | +0.235R | +3$ | +138$ |
| MINAUSDT | 2 | 100.0% | inf | +0.707R | +55$ | +110$ |
| UNIUSDT | 6 | 16.7% | 1.61 | +0.078R | +17$ | +103$ |
| STORJUSDT | 1 | 100.0% | inf | +1.354R | +101$ | +101$ |
| SFPUSDT | 6 | 33.3% | 1.87 | +0.254R | +16$ | +94$ |
| FILUSDT | 2 | 100.0% | inf | +0.502R | +41$ | +83$ |
| MASKUSDT | 7 | 28.6% | 1.40 | +0.048R | +11$ | +77$ |
| FTTUSDT | 4 | 25.0% | 1.39 | +0.049R | +17$ | +69$ |
| LOOMUSDT | 1 | 100.0% | inf | +0.605R | +58$ | +58$ |
| DASHUSDT | 6 | 33.3% | 1.50 | +0.155R | +8$ | +50$ |
| ETCUSDT | 13 | 30.8% | 1.10 | -0.126R | +4$ | +46$ |
| SOLUSDT | 15 | 33.3% | 1.09 | +0.216R | +3$ | +40$ |
| BANDUSDT | 5 | 20.0% | 1.26 | -0.082R | +6$ | +32$ |
| CHZUSDT | 6 | 33.3% | 1.11 | +0.081R | +4$ | +27$ |
| SUIUSDT | 5 | 20.0% | 0.97 | -0.146R | -1$ | -4$ |
| INJUSDT | 3 | 66.7% | 0.85 | -0.007R | -2$ | -7$ |
| ONEUSDT | 3 | 33.3% | 0.97 | -0.142R | -2$ | -7$ |
| MOVRUSDT | 1 | 0.0% | 0.00 | -0.120R | -8$ | -8$ |
| GMTUSDT | 2 | 50.0% | 0.60 | -0.389R | -7$ | -14$ |
| EOSUSDT | 1 | 0.0% | 0.00 | -1.000R | -15$ | -15$ |
| TRBUSDT | 1 | 0.0% | 0.00 | -0.344R | -26$ | -26$ |
| PHAUSDT | 1 | 0.0% | 0.00 | -0.456R | -27$ | -27$ |
| RUNEUSDT | 3 | 66.7% | 0.40 | -0.236R | -12$ | -35$ |
| GASUSDT | 3 | 33.3% | 0.25 | -0.161R | -16$ | -48$ |
| OPUSDT | 4 | 0.0% | 0.00 | -0.188R | -13$ | -50$ |
| SEIUSDT | 2 | 0.0% | 0.00 | -1.000R | -26$ | -51$ |
| STXUSDT | 1 | 0.0% | 0.00 | -0.635R | -52$ | -52$ |
| LDOUSDT | 3 | 33.3% | 0.52 | -0.260R | -20$ | -61$ |
| CYBERUSDT | 1 | 0.0% | 0.00 | -1.000R | -64$ | -64$ |
| ENAUSDT | 5 | 40.0% | 0.38 | -0.301R | -14$ | -68$ |
| APEUSDT | 1 | 0.0% | 0.00 | -1.000R | -68$ | -68$ |
| ENJUSDT | 2 | 0.0% | 0.00 | -0.697R | -34$ | -68$ |
| KITEUSDT | 2 | 0.0% | 0.00 | -0.891R | -35$ | -70$ |
| TWTUSDT | 4 | 25.0% | 0.29 | -0.416R | -19$ | -75$ |
| CAKEUSDT | 6 | 16.7% | 0.69 | -0.410R | -13$ | -77$ |
| QNTUSDT | 3 | 0.0% | 0.00 | -0.678R | -33$ | -100$ |
| RAYUSDT | 2 | 0.0% | 0.00 | -0.887R | -51$ | -103$ |
| ARKUSDT | 3 | 0.0% | 0.00 | -0.485R | -40$ | -121$ |
| WLDUSDT | 2 | 0.0% | 0.00 | -1.000R | -61$ | -123$ |
| FETUSDT | 4 | 0.0% | 0.00 | -0.600R | -33$ | -133$ |
| HBARUSDT | 8 | 25.0% | 0.12 | -0.458R | -17$ | -137$ |
| GALAUSDT | 4 | 25.0% | 0.11 | -0.367R | -35$ | -141$ |
| XMRUSDT | 5 | 40.0% | 0.05 | -0.464R | -29$ | -147$ |
| XLMUSDT | 5 | 0.0% | 0.00 | -0.650R | -30$ | -151$ |
| ENSUSDT | 6 | 16.7% | 0.02 | -0.589R | -28$ | -165$ |
| LUNAUSDT~20220513 | 7 | 14.3% | 0.61 | -0.406R | -25$ | -172$ |
| TAOUSDT | 5 | 0.0% | 0.00 | -1.000R | -37$ | -183$ |
| DOTUSDT | 4 | 0.0% | 0.00 | -0.526R | -46$ | -183$ |
| ICPUSDT | 6 | 16.7% | 0.28 | -0.412R | -34$ | -202$ |
| OMUSDT | 5 | 0.0% | 0.00 | -0.821R | -41$ | -206$ |
| RNDRUSDT | 5 | 20.0% | 0.04 | -0.501R | -41$ | -207$ |
| COCOSUSDT | 3 | 0.0% | 0.00 | -0.556R | -71$ | -214$ |
| LRCUSDT | 2 | 0.0% | 0.00 | -0.830R | -111$ | -223$ |
| MANAUSDT | 4 | 25.0% | 0.08 | -0.478R | -58$ | -230$ |
| BATUSDT | 3 | 0.0% | 0.00 | -0.894R | -82$ | -245$ |
| DYDXUSDT | 9 | 33.3% | 0.10 | -0.539R | -27$ | -246$ |
| CHRUSDT | 3 | 0.0% | 0.00 | -0.697R | -90$ | -269$ |
| ARBUSDT | 6 | 0.0% | 0.00 | -0.650R | -47$ | -283$ |
| MATICUSDT | 5 | 0.0% | 0.00 | -0.598R | -57$ | -284$ |
| IOTXUSDT | 4 | 25.0% | 0.19 | -0.553R | -72$ | -287$ |
| ROSEUSDT | 7 | 28.6% | 0.32 | -0.414R | -44$ | -305$ |
| BAKEUSDT | 8 | 25.0% | 0.14 | -0.568R | -42$ | -339$ |
| LTCUSDT | 17 | 17.6% | 0.16 | -0.442R | -20$ | -340$ |
| FTMUSDT | 13 | 38.5% | 0.36 | -0.315R | -28$ | -358$ |
| SANDUSDT | 5 | 0.0% | 0.00 | -0.580R | -73$ | -363$ |
| ADAUSDT | 19 | 15.8% | 0.38 | -0.133R | -23$ | -432$ |
| ALGOUSDT | 10 | 10.0% | 0.10 | -0.671R | -46$ | -464$ |
| ETHUSDT | 24 | 20.8% | 0.36 | -0.382R | -20$ | -488$ |
| CRVUSDT | 12 | 8.3% | 0.09 | -0.549R | -44$ | -529$ |
| ATOMUSDT | 13 | 15.4% | 0.22 | -0.487R | -48$ | -619$ |
| AVAXUSDT | 22 | 22.7% | 0.20 | -0.518R | -47$ | -1,026$ |

### BASE

**Walk-forward windows**

| Window | Chosen config | Train trades | Train exp. | Test trades | Test exp. | Test PF | Median config test exp. | Configs positive in test |
|---|---|---|---|---|---|---|---|---|
| train 2020-01→2022-01, test 2022-01→2023-01 | `BASE 1d [adx_min=15 adx_rise=3 swing=10] exit=3R` | 71 | +1.754R | 54 | -0.732R | 0.20 | -0.287R | 0.0% |
| train 2021-01→2023-01, test 2023-01→2024-01 | `BASE 1d [adx_min=15 adx_rise=3 swing=10] exit=trail3ATR` | 112 | +0.416R | 82 | -0.102R | 0.58 | +0.084R | 81.2% |
| train 2022-01→2024-01, test 2024-01→2025-01 | `BASE 1d [adx_min=15 adx_rise=3 swing=10] exit=trail3ATR` | 131 | +0.024R | 35 | +0.301R | 1.82 | +0.007R | 53.1% |
| train 2023-01→2025-01, test 2025-01→2026-01 | `BASE 1d [adx_min=15 adx_rise=5 swing=10] exit=3R` | 96 | +0.634R | 40 | -0.464R | 0.43 | -0.312R | 9.4% |
| train 2024-01→2026-01, test 2026-01→2026-09 | `BASE 1d [adx_min=15 adx_rise=5 swing=10] exit=2R` | 83 | +0.266R | 62 | +0.220R | 1.43 | +0.151R | 93.8% |

**By market regime (OOS)**

| Regime | Trades | Win rate | Profit factor | Expectancy | Exp. $/trade | Net P&L |
|---|---|---|---|---|---|---|
| BTC<200D | 133 | 27.8% | 0.43 | -0.241R | -33$ | -4,405$ |
| BTC>200D | 140 | 35.7% | 0.70 | -0.073R | -10$ | -1,435$ |

**By market regime (spec rules, full history)**

| Regime | Trades | Win rate | Profit factor | Expectancy | Exp. $/trade | Net P&L |
|---|---|---|---|---|---|---|
| BTC<200D | 167 | 44.3% | 1.31 | +0.275R | +38$ | +6,382$ |
| BTC>200D | 162 | 38.9% | 1.04 | +0.136R | +6$ | +896$ |

**By year (OOS)**

| Year | Trades | Win rate | Profit factor | Expectancy | Exp. $/trade | Net P&L |
|---|---|---|---|---|---|---|
| 2022 | 54 | 7.4% | 0.20 | -0.732R | -88$ | -4,746$ |
| 2023 | 82 | 39.0% | 0.58 | -0.102R | -11$ | -901$ |
| 2024 | 35 | 45.7% | 1.82 | +0.301R | +16$ | +576$ |
| 2025 | 40 | 15.0% | 0.43 | -0.464R | -33$ | -1,333$ |
| 2026 | 62 | 46.8% | 1.43 | +0.220R | +9$ | +563$ |

**By year (spec rules, full history 2020→, not walk-forward)**

| Year | Trades | Win rate | Profit factor | Expectancy | Exp. $/trade | Net P&L |
|---|---|---|---|---|---|---|
| 2020 | 44 | 56.8% | 2.67 | +0.787R | +126$ | +5,562$ |
| 2021 | 27 | 66.7% | 3.52 | +0.951R | +203$ | +5,485$ |
| 2022 | 56 | 21.4% | 0.39 | -0.496R | -133$ | -7,440$ |
| 2023 | 65 | 35.4% | 0.98 | +0.081R | -3$ | -163$ |
| 2024 | 31 | 58.1% | 2.74 | +0.786R | +138$ | +4,267$ |
| 2025 | 35 | 28.6% | 0.66 | -0.255R | -61$ | -2,136$ |
| 2026 | 71 | 43.7% | 1.24 | +0.209R | +24$ | +1,702$ |

**By coin (OOS, sorted by net P&L)**

| Coin | Trades | Win rate | Profit factor | Expectancy | Exp. $/trade | Net P&L |
|---|---|---|---|---|---|---|
| CHZUSDT | 3 | 100.0% | inf | +1.998R | +263$ | +789$ |
| ETCUSDT | 5 | 40.0% | 1.98 | +0.791R | +55$ | +274$ |
| WLDUSDT | 4 | 75.0% | 6.58 | +1.063R | +67$ | +268$ |
| ETHUSDT | 3 | 66.7% | 6.20 | +1.272R | +80$ | +241$ |
| ARBUSDT | 4 | 50.0% | 2.22 | +0.969R | +42$ | +167$ |
| BCHUSDT | 2 | 50.0% | 10.86 | +0.667R | +78$ | +155$ |
| BAKEUSDT | 1 | 100.0% | inf | +2.079R | +125$ | +125$ |
| MIRAUSDT | 2 | 100.0% | inf | +1.318R | +62$ | +124$ |
| MATICUSDT | 2 | 50.0% | 5.42 | +1.088R | +59$ | +118$ |
| TWTUSDT | 3 | 33.3% | 1.82 | +0.804R | +35$ | +105$ |
| CRVUSDT | 6 | 50.0% | 1.48 | +0.348R | +17$ | +101$ |
| UNIUSDT | 7 | 28.6% | 1.60 | +0.165R | +13$ | +94$ |
| VIRTUALUSDT | 1 | 100.0% | inf | +1.962R | +86$ | +86$ |
| ENSOUSDT | 1 | 100.0% | inf | +1.958R | +85$ | +85$ |
| WALUSDT | 1 | 100.0% | inf | +1.964R | +84$ | +84$ |
| FFUSDT | 1 | 100.0% | inf | +1.955R | +82$ | +82$ |
| STRKUSDT | 2 | 50.0% | 2.35 | +0.484R | +31$ | +62$ |
| MDXUSDT | 5 | 60.0% | 5.90 | +0.087R | +12$ | +60$ |
| LTCUSDT | 5 | 40.0% | 2.20 | -0.125R | +11$ | +56$ |
| INJUSDT | 1 | 100.0% | inf | +0.967R | +55$ | +55$ |
| LAZIOUSDT | 4 | 75.0% | 2.74 | +0.217R | +13$ | +51$ |
| KITEUSDT | 1 | 100.0% | inf | +0.882R | +46$ | +46$ |
| SEIUSDT | 1 | 100.0% | inf | +1.932R | +36$ | +36$ |
| WLFIUSDT | 2 | 50.0% | 1.61 | +0.473R | +16$ | +32$ |
| ZBTUSDT | 3 | 33.3% | 1.51 | +0.264R | +9$ | +28$ |
| BTCUSDT | 2 | 50.0% | 1.51 | +0.446R | +14$ | +28$ |
| ASTERUSDT | 3 | 33.3% | 1.43 | -0.019R | +9$ | +26$ |
| FORMUSDT | 1 | 100.0% | inf | +0.202R | +9$ | +9$ |
| XPLUSDT | 1 | 100.0% | inf | +0.142R | +6$ | +6$ |
| ORDIUSDT | 1 | 100.0% | inf | +0.078R | +5$ | +5$ |
| TRBUSDT | 3 | 33.3% | 1.02 | -0.013R | +0$ | +1$ |
| 2ZUSDT | 1 | 0.0% | 0.00 | -0.009R | -0$ | -0$ |
| ATUSDT | 1 | 0.0% | 0.00 | -0.065R | -3$ | -3$ |
| HBARUSDT | 1 | 0.0% | 0.00 | -1.000R | -5$ | -5$ |
| FTTUSDT | 7 | 28.6% | 0.94 | +0.173R | -2$ | -17$ |
| PHAUSDT | 8 | 50.0% | 0.83 | -0.045R | -2$ | -18$ |
| AVNTUSDT | 2 | 50.0% | 0.58 | -0.196R | -10$ | -20$ |
| STORJUSDT | 2 | 50.0% | 0.17 | -0.178R | -11$ | -22$ |
| WAVESUSDT | 1 | 0.0% | 0.00 | -0.362R | -26$ | -26$ |
| HFTUSDT | 3 | 33.3% | 0.71 | -0.219R | -10$ | -30$ |
| MMTUSDT | 2 | 50.0% | 0.32 | -0.332R | -16$ | -32$ |
| STXUSDT | 2 | 50.0% | 0.26 | -0.274R | -16$ | -32$ |
| LOOMUSDT | 1 | 0.0% | 0.00 | -0.572R | -37$ | -37$ |
| SFPUSDT | 2 | 50.0% | 0.18 | -0.274R | -19$ | -39$ |
| MASKUSDT | 1 | 0.0% | 0.00 | -0.759R | -44$ | -44$ |
| HEMIUSDT | 1 | 0.0% | 0.00 | -1.000R | -46$ | -46$ |
| XLMUSDT | 1 | 0.0% | 0.00 | -1.000R | -46$ | -46$ |
| BANDUSDT | 3 | 33.3% | 0.02 | -0.295R | -17$ | -51$ |
| THEUSDT | 2 | 50.0% | 0.21 | -0.366R | -27$ | -53$ |
| ZKUSDT | 1 | 0.0% | 0.00 | -1.000R | -54$ | -54$ |
| ATOMUSDT | 1 | 0.0% | 0.00 | -0.729R | -55$ | -55$ |
| ZECUSDT | 2 | 50.0% | 0.59 | +0.483R | -30$ | -59$ |
| LUNAUSDT | 8 | 37.5% | 0.75 | +0.177R | -8$ | -60$ |
| ARUSDT | 1 | 0.0% | 0.00 | -0.869R | -61$ | -61$ |
| TONUSDT | 1 | 0.0% | 0.00 | -1.000R | -62$ | -62$ |
| QNTUSDT | 2 | 0.0% | 0.00 | -0.493R | -32$ | -65$ |
| USUALUSDT | 1 | 0.0% | 0.00 | -1.000R | -67$ | -67$ |
| YFIIUSDT | 1 | 0.0% | 0.00 | -0.826R | -68$ | -68$ |
| TAOUSDT | 3 | 33.3% | 0.21 | -0.404R | -23$ | -69$ |
| RENDERUSDT | 1 | 0.0% | 0.00 | -1.000R | -72$ | -72$ |
| ARKMUSDT | 1 | 0.0% | 0.00 | -1.000R | -72$ | -72$ |
| RAYUSDT | 1 | 0.0% | 0.00 | -1.000R | -74$ | -74$ |
| ETHFIUSDT | 1 | 0.0% | 0.00 | -1.000R | -74$ | -74$ |
| EIGENUSDT | 1 | 0.0% | 0.00 | -1.000R | -75$ | -75$ |
| GMTUSDT | 4 | 25.0% | 0.26 | -0.258R | -19$ | -76$ |
| LINKUSDT | 2 | 50.0% | 0.27 | -0.319R | -40$ | -81$ |
| BNBUSDT | 5 | 60.0% | 0.65 | +0.533R | -17$ | -83$ |
| HOOKUSDT | 2 | 0.0% | 0.00 | -0.639R | -42$ | -84$ |
| GALAUSDT | 5 | 40.0% | 0.47 | -0.170R | -17$ | -86$ |
| MOVRUSDT | 2 | 0.0% | 0.00 | -0.706R | -45$ | -90$ |
| ZENUSDT | 2 | 0.0% | 0.00 | -1.000R | -48$ | -95$ |
| KLAYUSDT | 2 | 0.0% | 0.00 | -0.676R | -51$ | -101$ |
| OPUSDT | 3 | 33.3% | 0.35 | -0.380R | -34$ | -103$ |
| EOSUSDT | 1 | 0.0% | 0.00 | -1.000R | -109$ | -109$ |
| MANAUSDT | 1 | 0.0% | 0.00 | -1.000R | -110$ | -110$ |
| XRPUSDT | 4 | 25.0% | 0.28 | -0.411R | -28$ | -113$ |
| FETUSDT | 4 | 25.0% | 0.31 | -0.503R | -29$ | -115$ |
| ROSEUSDT | 1 | 0.0% | 0.00 | -1.000R | -118$ | -118$ |
| JASMYUSDT | 2 | 0.0% | 0.00 | -1.000R | -61$ | -122$ |
| ENAUSDT | 2 | 0.0% | 0.00 | -1.000R | -62$ | -124$ |
| DOTUSDT | 3 | 33.3% | 0.27 | -0.452R | -45$ | -136$ |
| APTUSDT | 6 | 33.3% | 0.44 | -0.272R | -23$ | -138$ |
| APEUSDT | 3 | 33.3% | 0.03 | -0.612R | -47$ | -140$ |
| TIAUSDT | 2 | 0.0% | 0.00 | -1.000R | -72$ | -145$ |
| EGLDUSDT | 1 | 0.0% | 0.00 | -1.000R | -148$ | -148$ |
| SLPUSDT | 1 | 0.0% | 0.00 | -1.000R | -148$ | -148$ |
| OMGUSDT | 1 | 0.0% | 0.00 | -1.000R | -149$ | -149$ |
| MOVEUSDT | 2 | 0.0% | 0.00 | -1.000R | -76$ | -152$ |
| VETUSDT | 1 | 0.0% | 0.00 | -1.000R | -155$ | -155$ |
| AXSUSDT | 3 | 33.3% | 0.22 | -0.479R | -52$ | -157$ |
| SANDUSDT | 3 | 0.0% | 0.00 | -0.707R | -53$ | -159$ |
| ALGOUSDT | 2 | 0.0% | 0.00 | -0.828R | -83$ | -166$ |
| SOLUSDT | 2 | 0.0% | 0.00 | -1.000R | -84$ | -168$ |
| ONEUSDT | 1 | 0.0% | 0.00 | -1.000R | -176$ | -176$ |
| NEARUSDT | 6 | 33.3% | 0.38 | -0.305R | -30$ | -182$ |
| DARUSDT | 2 | 0.0% | 0.00 | -1.000R | -91$ | -182$ |
| TRXUSDT | 2 | 0.0% | 0.00 | -1.000R | -102$ | -204$ |
| AVAXUSDT | 4 | 25.0% | 0.17 | -0.570R | -51$ | -204$ |
| SUSHIUSDT | 4 | 0.0% | 0.00 | -0.848R | -59$ | -235$ |
| FILUSDT | 5 | 20.0% | 0.06 | -0.716R | -49$ | -245$ |
| IOTXUSDT | 2 | 0.0% | 0.00 | -1.000R | -124$ | -248$ |
| ADAUSDT | 4 | 0.0% | 0.00 | -0.793R | -63$ | -252$ |
| HOTUSDT | 2 | 0.0% | 0.00 | -1.000R | -127$ | -254$ |
| TLMUSDT | 2 | 0.0% | 0.00 | -1.000R | -130$ | -260$ |
| FTMUSDT | 2 | 0.0% | 0.00 | -1.000R | -151$ | -303$ |
| DYDXUSDT | 3 | 0.0% | 0.00 | -0.805R | -103$ | -310$ |
| COCOSUSDT | 3 | 0.0% | 0.00 | -0.946R | -114$ | -341$ |
| MBOXUSDT | 3 | 0.0% | 0.00 | -1.000R | -124$ | -373$ |
| ICPUSDT | 8 | 25.0% | 0.31 | -0.263R | -49$ | -394$ |

### BREAKOUT

**Walk-forward windows**

| Window | Chosen config | Train trades | Train exp. | Test trades | Test exp. | Test PF | Median config test exp. | Configs positive in test |
|---|---|---|---|---|---|---|---|---|
| train 2020-01→2022-01, test 2022-01→2023-01 | `BREAKOUT 1d [lookback=20 swing=20 vol_mult=1.5] exit=3R` | 224 | +1.564R | 82 | -0.740R | 0.11 | -0.490R | 0.0% |
| train 2021-01→2023-01, test 2023-01→2024-01 | `BREAKOUT 4h [lookback=20 swing=20 vol_mult=2.0] exit=3R` | 460 | +0.261R | 141 | +0.264R | 1.39 | +0.314R | 87.5% |
| train 2022-01→2024-01, test 2024-01→2025-01 | `BREAKOUT 1d [lookback=20 swing=20 vol_mult=2.0] exit=trail3ATR` | 263 | +0.076R | 166 | +0.024R | 1.00 | +0.040R | 75.0% |
| train 2023-01→2025-01, test 2025-01→2026-01 | `BREAKOUT 4h [lookback=20 swing=20 vol_mult=1.5] exit=3R` | 325 | +0.358R | 172 | -0.401R | 0.42 | -0.324R | 0.0% |
| train 2024-01→2026-01, test 2026-01→2026-09 | `BREAKOUT 1d [lookback=20 swing=20 vol_mult=1.5] exit=trail3ATR` | 310 | -0.019R | 139 | +0.022R | 0.90 | +0.101R | 96.9% |

**By market regime (OOS)**

| Regime | Trades | Win rate | Profit factor | Expectancy | Exp. $/trade | Net P&L |
|---|---|---|---|---|---|---|
| BTC<200D | 303 | 25.1% | 0.56 | -0.070R | -15$ | -4,411$ |
| BTC>200D | 397 | 28.5% | 0.63 | -0.162R | -10$ | -3,964$ |

**By market regime (spec rules, full history)**

| Regime | Trades | Win rate | Profit factor | Expectancy | Exp. $/trade | Net P&L |
|---|---|---|---|---|---|---|
| BTC<200D | 246 | 38.6% | 1.01 | +0.186R | +2$ | +459$ |
| BTC>200D | 528 | 45.5% | 1.08 | +0.298R | +20$ | +10,769$ |

**By year (OOS)**

| Year | Trades | Win rate | Profit factor | Expectancy | Exp. $/trade | Net P&L |
|---|---|---|---|---|---|---|
| 2022 | 82 | 6.1% | 0.11 | -0.740R | -80$ | -6,521$ |
| 2023 | 141 | 34.8% | 1.39 | +0.264R | +11$ | +1,610$ |
| 2024 | 166 | 38.0% | 1.00 | +0.024R | +0$ | +6$ |
| 2025 | 172 | 15.7% | 0.42 | -0.401R | -20$ | -3,393$ |
| 2026 | 139 | 32.4% | 0.90 | +0.022R | -1$ | -78$ |

**By year (spec rules, full history 2020→, not walk-forward)**

| Year | Trades | Win rate | Profit factor | Expectancy | Exp. $/trade | Net P&L |
|---|---|---|---|---|---|---|
| 2020 | 124 | 59.7% | 2.28 | +0.833R | +119$ | +14,752$ |
| 2021 | 164 | 51.8% | 1.56 | +0.615R | +231$ | +37,803$ |
| 2022 | 85 | 9.4% | 0.13 | -0.727R | -466$ | -39,639$ |
| 2023 | 119 | 50.4% | 1.71 | +0.477R | +105$ | +12,501$ |
| 2024 | 121 | 38.0% | 0.80 | +0.062R | -53$ | -6,376$ |
| 2025 | 75 | 30.7% | 0.54 | -0.182R | -120$ | -9,027$ |
| 2026 | 86 | 45.3% | 1.13 | +0.119R | +14$ | +1,214$ |

**By coin (OOS, sorted by net P&L)**

| Coin | Trades | Win rate | Profit factor | Expectancy | Exp. $/trade | Net P&L |
|---|---|---|---|---|---|---|
| BTCUSDT | 17 | 41.2% | 2.59 | +0.400R | +22$ | +371$ |
| WLDUSDT | 13 | 23.1% | 2.51 | +0.196R | +23$ | +294$ |
| AXSUSDT | 10 | 40.0% | 1.59 | +0.635R | +25$ | +246$ |
| SFPUSDT | 5 | 60.0% | 2.89 | +1.474R | +44$ | +218$ |
| KLAYUSDT | 2 | 100.0% | inf | +2.032R | +99$ | +198$ |
| TWTUSDT | 4 | 50.0% | 3.39 | +0.965R | +49$ | +197$ |
| BANDUSDT | 3 | 66.7% | 4.57 | +1.279R | +59$ | +177$ |
| SUIUSDT | 9 | 44.4% | 4.42 | +0.461R | +19$ | +173$ |
| FETUSDT | 10 | 40.0% | 2.53 | +0.334R | +17$ | +166$ |
| MDXUSDT | 1 | 100.0% | inf | +2.893R | +144$ | +144$ |
| SOLUSDT | 12 | 41.7% | 1.78 | +0.389R | +11$ | +126$ |
| RNDRUSDT | 3 | 66.7% | 12.37 | +0.518R | +38$ | +115$ |
| EIGENUSDT | 1 | 100.0% | inf | +2.955R | +108$ | +108$ |
| FILUSDT | 13 | 30.8% | 1.47 | +0.199R | +7$ | +93$ |
| SEIUSDT | 9 | 55.6% | 1.76 | +0.339R | +10$ | +87$ |
| XLMUSDT | 8 | 25.0% | 1.39 | -0.233R | +8$ | +65$ |
| ARUSDT | 3 | 33.3% | 1.65 | +0.599R | +19$ | +58$ |
| DASHUSDT | 4 | 75.0% | 34.32 | +0.591R | +13$ | +51$ |
| ETCUSDT | 12 | 33.3% | 1.10 | -0.101R | +3$ | +33$ |
| BNBUSDT | 19 | 36.8% | 1.07 | +0.169R | +1$ | +26$ |
| TAOUSDT | 6 | 33.3% | 1.19 | +0.296R | +4$ | +26$ |
| MINAUSDT | 4 | 50.0% | 1.35 | +0.162R | +5$ | +22$ |
| AVAXUSDT | 19 | 31.6% | 1.04 | +0.234R | +1$ | +20$ |
| ATOMUSDT | 9 | 44.4% | 1.06 | +0.301R | +2$ | +18$ |
| FFUSDT | 3 | 66.7% | 4.77 | +0.278R | +6$ | +17$ |
| PHAUSDT | 4 | 25.0% | 1.12 | -0.017R | +4$ | +15$ |
| JASMYUSDT | 5 | 20.0% | 1.11 | -0.045R | +3$ | +15$ |
| ETHUSDT | 12 | 33.3% | 1.05 | +0.075R | +1$ | +9$ |
| JTOUSDT | 1 | 100.0% | inf | +0.127R | +8$ | +8$ |
| ASTERUSDT | 1 | 100.0% | inf | +1.472R | +5$ | +5$ |
| WALUSDT | 1 | 100.0% | inf | +0.045R | +1$ | +1$ |
| ROSEUSDT | 3 | 33.3% | 1.00 | +0.320R | -0$ | -1$ |
| VIRTUALUSDT | 3 | 66.7% | 0.67 | -0.059R | -1$ | -3$ |
| ATUSDT | 1 | 0.0% | 0.00 | -0.174R | -3$ | -3$ |
| XMRUSDT | 1 | 0.0% | 0.00 | -1.000R | -3$ | -3$ |
| ENSOUSDT | 1 | 0.0% | 0.00 | -0.205R | -4$ | -4$ |
| CAKEUSDT | 11 | 27.3% | 0.96 | +0.262R | -1$ | -6$ |
| KITEUSDT | 1 | 0.0% | 0.00 | -0.294R | -6$ | -6$ |
| MIRAUSDT | 1 | 0.0% | 0.00 | -0.301R | -7$ | -7$ |
| METUSDT | 2 | 0.0% | 0.00 | -0.173R | -4$ | -7$ |
| GASUSDT | 1 | 0.0% | 0.00 | -0.115R | -8$ | -8$ |
| XPLUSDT | 1 | 0.0% | 0.00 | -0.427R | -9$ | -9$ |
| POLUSDT | 1 | 0.0% | 0.00 | -1.000R | -9$ | -9$ |
| MMTUSDT | 2 | 0.0% | 0.00 | -0.230R | -4$ | -9$ |
| ZKUSDT | 2 | 50.0% | 0.22 | -0.198R | -4$ | -9$ |
| AVNTUSDT | 1 | 0.0% | 0.00 | -0.503R | -9$ | -9$ |
| 2ZUSDT | 1 | 0.0% | 0.00 | -0.532R | -11$ | -11$ |
| APTUSDT | 13 | 30.8% | 0.97 | -0.170R | -1$ | -13$ |
| STRKUSDT | 2 | 0.0% | 0.00 | -0.343R | -8$ | -15$ |
| HEMIUSDT | 2 | 0.0% | 0.00 | -0.397R | -8$ | -15$ |
| ETHFIUSDT | 1 | 0.0% | 0.00 | -1.000R | -16$ | -16$ |
| THEUSDT | 4 | 50.0% | 0.82 | +0.390R | -5$ | -19$ |
| STXUSDT | 5 | 40.0% | 0.82 | -0.035R | -5$ | -23$ |
| ZBTUSDT | 2 | 0.0% | 0.00 | -0.601R | -12$ | -23$ |
| TRXUSDT | 9 | 55.6% | 0.81 | +0.572R | -3$ | -27$ |
| LOOMUSDT | 3 | 0.0% | 0.00 | -0.115R | -10$ | -29$ |
| ZENUSDT | 4 | 0.0% | 0.00 | -0.331R | -7$ | -29$ |
| TRBUSDT | 3 | 33.3% | 0.47 | -0.174R | -10$ | -31$ |
| LDOUSDT | 3 | 33.3% | 0.11 | -0.164R | -11$ | -32$ |
| FORMUSDT | 4 | 25.0% | 0.10 | -0.396R | -8$ | -33$ |
| ENSUSDT | 3 | 0.0% | 0.00 | -0.708R | -12$ | -35$ |
| MASKUSDT | 4 | 50.0% | 0.65 | +0.425R | -9$ | -35$ |
| BCHUSDT | 11 | 36.4% | 0.85 | +0.003R | -3$ | -37$ |
| MATICUSDT | 4 | 25.0% | 0.21 | -0.332R | -11$ | -44$ |
| BAKEUSDT | 4 | 50.0% | 0.08 | -0.203R | -14$ | -58$ |
| DARUSDT | 1 | 0.0% | 0.00 | -1.000R | -61$ | -61$ |
| NEARUSDT | 11 | 45.5% | 0.69 | +0.347R | -6$ | -69$ |
| YFIIUSDT | 2 | 0.0% | 0.00 | -1.000R | -37$ | -73$ |
| ORDIUSDT | 7 | 28.6% | 0.58 | -0.145R | -11$ | -76$ |
| QNTUSDT | 3 | 0.0% | 0.00 | -1.000R | -26$ | -79$ |
| UNIUSDT | 11 | 45.5% | 0.27 | +0.057R | -7$ | -80$ |
| MOVRUSDT | 4 | 25.0% | 0.30 | -0.234R | -20$ | -81$ |
| ALICEUSDT | 1 | 0.0% | 0.00 | -1.000R | -89$ | -89$ |
| RUNEUSDT | 8 | 25.0% | 0.65 | -0.115R | -11$ | -90$ |
| CYBERUSDT | 3 | 0.0% | 0.00 | -0.421R | -31$ | -92$ |
| LAZIOUSDT | 2 | 0.0% | 0.00 | -1.000R | -49$ | -99$ |
| GMTUSDT | 9 | 22.2% | 0.67 | -0.101R | -11$ | -100$ |
| LINKUSDT | 16 | 43.8% | 0.81 | +0.049R | -6$ | -103$ |
| DYDXUSDT | 9 | 11.1% | 0.69 | -0.218R | -12$ | -105$ |
| LTCUSDT | 16 | 18.8% | 0.74 | -0.372R | -7$ | -105$ |
| MOVEUSDT | 2 | 0.0% | 0.00 | -1.000R | -55$ | -109$ |
| ARKUSDT | 3 | 0.0% | 0.00 | -0.515R | -37$ | -111$ |
| ARKMUSDT | 3 | 0.0% | 0.00 | -1.000R | -38$ | -114$ |
| APEUSDT | 8 | 12.5% | 0.55 | -0.520R | -15$ | -121$ |
| LUNAUSDT~20220513 | 1 | 0.0% | 0.00 | -1.000R | -126$ | -126$ |
| RENDERUSDT | 3 | 0.0% | 0.00 | -1.000R | -42$ | -126$ |
| HFTUSDT | 2 | 0.0% | 0.00 | -1.000R | -63$ | -126$ |
| OMGUSDT | 1 | 0.0% | 0.00 | -1.000R | -127$ | -127$ |
| IOTXUSDT | 1 | 0.0% | 0.00 | -1.000R | -131$ | -131$ |
| TLMUSDT | 1 | 0.0% | 0.00 | -1.000R | -132$ | -132$ |
| MANAUSDT | 1 | 0.0% | 0.00 | -1.000R | -132$ | -132$ |
| SLPUSDT | 1 | 0.0% | 0.00 | -1.000R | -133$ | -133$ |
| CHZUSDT | 6 | 33.3% | 0.59 | -0.128R | -22$ | -133$ |
| GALAUSDT | 5 | 40.0% | 0.20 | -0.326R | -27$ | -133$ |
| STORJUSDT | 5 | 0.0% | 0.00 | -0.342R | -27$ | -136$ |
| HOTUSDT | 1 | 0.0% | 0.00 | -1.000R | -137$ | -137$ |
| ONEUSDT | 1 | 0.0% | 0.00 | -1.000R | -150$ | -150$ |
| DOTUSDT | 11 | 27.3% | 0.54 | -0.230R | -14$ | -151$ |
| RAYUSDT | 4 | 0.0% | 0.00 | -1.000R | -39$ | -155$ |
| THETAUSDT | 2 | 0.0% | 0.00 | -1.000R | -78$ | -156$ |
| BATUSDT | 2 | 0.0% | 0.00 | -1.000R | -79$ | -157$ |
| SUSHIUSDT | 2 | 0.0% | 0.00 | -1.000R | -82$ | -164$ |
| USUALUSDT | 4 | 0.0% | 0.00 | -0.828R | -44$ | -177$ |
| ENAUSDT | 8 | 12.5% | 0.08 | -0.505R | -22$ | -178$ |
| XRPUSDT | 14 | 21.4% | 0.61 | -0.277R | -13$ | -178$ |
| OMUSDT | 4 | 0.0% | 0.00 | -0.910R | -45$ | -179$ |
| OPUSDT | 6 | 16.7% | 0.01 | -0.699R | -30$ | -180$ |
| TIAUSDT | 5 | 0.0% | 0.00 | -0.614R | -38$ | -188$ |
| EOSUSDT | 6 | 16.7% | 0.33 | -0.297R | -31$ | -188$ |
| LUNAUSDT | 6 | 16.7% | 0.20 | -0.458R | -31$ | -188$ |
| SANDUSDT | 4 | 0.0% | 0.00 | -1.000R | -50$ | -199$ |
| CHRUSDT | 2 | 0.0% | 0.00 | -1.000R | -101$ | -203$ |
| COCOSUSDT | 3 | 0.0% | 0.00 | -0.944R | -72$ | -217$ |
| ENJUSDT | 2 | 0.0% | 0.00 | -1.000R | -110$ | -221$ |
| LRCUSDT | 2 | 0.0% | 0.00 | -1.000R | -111$ | -223$ |
| TROYUSDT | 4 | 0.0% | 0.00 | -1.000R | -59$ | -237$ |
| FTMUSDT | 8 | 25.0% | 0.19 | -0.328R | -30$ | -237$ |
| ARBUSDT | 16 | 25.0% | 0.38 | -0.339R | -16$ | -249$ |
| INJUSDT | 7 | 0.0% | 0.00 | -0.668R | -37$ | -259$ |
| EGLDUSDT | 3 | 0.0% | 0.00 | -1.000R | -87$ | -262$ |
| ZECUSDT | 8 | 25.0% | 0.06 | -0.392R | -33$ | -267$ |
| HBARUSDT | 8 | 12.5% | 0.10 | -0.642R | -34$ | -273$ |
| ICPUSDT | 11 | 18.2% | 0.02 | -0.324R | -27$ | -301$ |
| CRVUSDT | 15 | 26.7% | 0.23 | -0.354R | -28$ | -418$ |
| ALGOUSDT | 15 | 20.0% | 0.27 | -0.402R | -32$ | -481$ |
| FTTUSDT | 9 | 0.0% | 0.00 | -0.588R | -56$ | -500$ |
| ADAUSDT | 24 | 20.8% | 0.42 | -0.395R | -25$ | -595$ |

## 4. Point-in-time universe

Each period trades only the coins that were the top by USDT volume over the 3 months *before* it started (excluded categories removed). Coins added / dropped versus the previous snapshot:

| Period start | Coins | Added | Dropped |
|---|---|---|---|
| 2020-01-01 | 50 | - | - |
| 2021-01-01 | 50 | ALPHAUSDT, BANDUSDT, CRVUSDT, CVCUSDT, DOTUSDT, EGLDUSDT, FILUSDT, INJUSDT, NEARUSDT, OCEANUSDT, OMGUSDT, RENUSDT, ROSEUSDT, RSRUSDT, SNXUSDT, SUSHIUSDT, SXPUSDT, THETAUSDT, TRBUSDT, UNFIUSDT, UNIUSDT, YFIIUSDT, YFIUSDT | ARPAUSDT, BATUSDT, BEAMUSDT, CELRUSDT, CHZUSDT, COCOSUSDT~20210119, DOCKUSDT, ENJUSDT, ERDUSDT, FETUSDT, HOTUSDT, ICXUSDT, IOTAUSDT, MATICUSDT, MCOUSDT, NKNUSDT, NPXSUSDT, ONEUSDT, RVNUSDT, STXUSDT, TOMOUSDT, TROYUSDT, ZRXUSDT |
| 2022-01-01 | 50 | ALICEUSDT, AVAXUSDT, AXSUSDT, BATUSDT, CHRUSDT, CHZUSDT, COCOSUSDT, DARUSDT, DYDXUSDT, ENJUSDT, FTMUSDT, FTTUSDT, GALAUSDT, HOTUSDT, ICPUSDT, IOTXUSDT, LRCUSDT, LUNAUSDT~20220513, MANAUSDT, MATICUSDT, MBOXUSDT, ONEUSDT, SANDUSDT, SLPUSDT, SOLUSDT, TLMUSDT | ALPHAUSDT, BANDUSDT, BCHUSDT, CVCUSDT, DASHUSDT, INJUSDT, IOSTUSDT, KAVAUSDT, NEOUSDT, OCEANUSDT, ONTUSDT, QTUMUSDT, RENUSDT, RSRUSDT, SNXUSDT, SXPUSDT, TRBUSDT, UNFIUSDT, UNIUSDT, WAVESUSDT, XLMUSDT, XMRUSDT, XTZUSDT, YFIIUSDT, YFIUSDT, ZILUSDT |
| 2023-01-01 | 50 | APEUSDT, APTUSDT, ARUSDT, BANDUSDT, ENSUSDT, GMTUSDT, HFTUSDT, HOOKUSDT, JASMYUSDT, KLAYUSDT, LAZIOUSDT, LUNAUSDT, MASKUSDT, MDXUSDT, OPUSDT, PHAUSDT, QNTUSDT, SFPUSDT, TWTUSDT, UNIUSDT, WAVESUSDT, XMRUSDT, YFIIUSDT | ALICEUSDT, BATUSDT, BTTUSDT, CHRUSDT, COCOSUSDT, DARUSDT, EGLDUSDT, ENJUSDT, HOTUSDT, ICPUSDT, IOTXUSDT, LRCUSDT, LUNAUSDT~20220513, MANAUSDT, MBOXUSDT, OMGUSDT, ONEUSDT, ROSEUSDT, SLPUSDT, THETAUSDT, TLMUSDT, VETUSDT, ZECUSDT |
| 2024-01-01 | 50 | ARBUSDT, ARKUSDT, BAKEUSDT, BCHUSDT, CAKEUSDT, CYBERUSDT, FETUSDT, GASUSDT, ICPUSDT, INJUSDT, JTOUSDT, LDOUSDT, LOOMUSDT, MINAUSDT, MOVRUSDT, ORDIUSDT, RNDRUSDT, RUNEUSDT, SEIUSDT, STORJUSDT, STXUSDT, SUIUSDT, TIAUSDT, TRBUSDT, WLDUSDT | ALGOUSDT, APEUSDT, ARUSDT, AXSUSDT, BANDUSDT, CHZUSDT, CRVUSDT, ENSUSDT, EOSUSDT, HFTUSDT, HOOKUSDT, JASMYUSDT, KLAYUSDT, LAZIOUSDT, MASKUSDT, MDXUSDT, PHAUSDT, QNTUSDT, SANDUSDT, SFPUSDT, SUSHIUSDT, TWTUSDT, WAVESUSDT, XMRUSDT, YFIIUSDT |
| 2024-09-30 | 50 | ARUSDT, BANANAUSDT, BNXUSDT, CKBUSDT, CRVUSDT, ENAUSDT, ENSUSDT, ETHFIUSDT, IOUSDT, JASMYUSDT, JUPUSDT, MKRUSDT, PENDLEUSDT, RAREUSDT, RENDERUSDT, SAGAUSDT, STRKUSDT, SUNUSDT, TAOUSDT, TONUSDT, ZKUSDT, ZROUSDT | ARKUSDT, ATOMUSDT, BAKEUSDT, CAKEUSDT, CYBERUSDT, DYDXUSDT, ETCUSDT, FTTUSDT, GASUSDT, GMTUSDT, JTOUSDT, LDOUSDT, LOOMUSDT, LUNAUSDT, MATICUSDT, MINAUSDT, MOVRUSDT, RNDRUSDT, STORJUSDT, STXUSDT, TRBUSDT, UNIUSDT |
| 2025-01-01 | 50 | ALGOUSDT, APEUSDT, ARKMUSDT, EIGENUSDT, ETCUSDT, HBARUSDT, MOVEUSDT, OMUSDT, POLUSDT, RAYUSDT, SANDUSDT, THEUSDT, TROYUSDT, UNIUSDT, USUALUSDT, XLMUSDT | ARUSDT, BANANAUSDT, BNXUSDT, CKBUSDT, ICPUSDT, IOUSDT, JASMYUSDT, JUPUSDT, MKRUSDT, PENDLEUSDT, RAREUSDT, SAGAUSDT, STRKUSDT, SUNUSDT, ZKUSDT, ZROUSDT |
| 2026-01-01 | 50 | 2ZUSDT, ASTERUSDT, ATUSDT, AVNTUSDT, CAKEUSDT, DASHUSDT, ENSOUSDT, FFUSDT, FORMUSDT, HEMIUSDT, ICPUSDT, KITEUSDT, METUSDT, MIRAUSDT, MMTUSDT, STRKUSDT, VIRTUALUSDT, WALUSDT, WLFIUSDT, XPLUSDT, ZBTUSDT, ZECUSDT, ZENUSDT, ZKUSDT | ALGOUSDT, APEUSDT, ARKMUSDT, EIGENUSDT, ENSUSDT, ETCUSDT, ETHFIUSDT, FTMUSDT, GALAUSDT, INJUSDT, MOVEUSDT, OMUSDT, OPUSDT, ORDIUSDT, POLUSDT, RAYUSDT, RENDERUSDT, RUNEUSDT, SANDUSDT, THEUSDT, TIAUSDT, TONUSDT, TROYUSDT, USUALUSDT |

Coins traded in some period that are **not** in today's top 50 (141): 2ZUSDT, ALGOUSDT, ALICEUSDT, ALPHAUSDT, APEUSDT, ARKMUSDT, ARKUSDT, ARPAUSDT, ARUSDT, ATOMUSDT, ATUSDT, AVNTUSDT, AXSUSDT, BAKEUSDT, BANANAUSDT, BANDUSDT, BATUSDT, BEAMUSDT, BNXUSDT, BTTUSDT, CAKEUSDT, CELRUSDT, CHRUSDT, CHZUSDT, CKBUSDT, COCOSUSDT, COCOSUSDT~20210119, CRVUSDT, CVCUSDT, CYBERUSDT, DARUSDT, DOCKUSDT, DYDXUSDT, EGLDUSDT, EIGENUSDT, ENJUSDT, ENSOUSDT, ENSUSDT, EOSUSDT, ERDUSDT, ETCUSDT, ETHFIUSDT, FFUSDT, FORMUSDT, FTMUSDT, FTTUSDT, GALAUSDT, GASUSDT, GMTUSDT, HFTUSDT, HOOKUSDT, HOTUSDT, ICPUSDT, ICXUSDT, IOSTUSDT, IOTAUSDT, IOTXUSDT, IOUSDT, JASMYUSDT, JTOUSDT, JUPUSDT, KAVAUSDT, KLAYUSDT, LAZIOUSDT, LDOUSDT, LOOMUSDT, LRCUSDT, LUNAUSDT, LUNAUSDT~20220513, MANAUSDT, MASKUSDT, MATICUSDT, MBOXUSDT, MCOUSDT, MDXUSDT, METUSDT, MINAUSDT, MIRAUSDT, MKRUSDT, MOVEUSDT, MOVRUSDT, NEOUSDT, NKNUSDT, NPXSUSDT, OCEANUSDT, OMGUSDT, OMUSDT, ONEUSDT, ONTUSDT, OPUSDT, ORDIUSDT, PENDLEUSDT, PHAUSDT, QTUMUSDT, RAREUSDT, RAYUSDT, RENDERUSDT, RENUSDT, RNDRUSDT, ROSEUSDT, RSRUSDT, RUNEUSDT, RVNUSDT, SAGAUSDT, SANDUSDT, SEIUSDT, SFPUSDT, SLPUSDT, SNXUSDT, STORJUSDT, STRKUSDT, STXUSDT, SUNUSDT, SUSHIUSDT, SXPUSDT, THETAUSDT, THEUSDT, TIAUSDT, TLMUSDT, TOMOUSDT, TONUSDT, TRBUSDT, TROYUSDT, TWTUSDT, UNFIUSDT, USUALUSDT, VETUSDT, VIRTUALUSDT, WALUSDT, WAVESUSDT, WLFIUSDT, XMRUSDT, XTZUSDT, YFIIUSDT, YFIUSDT, ZBTUSDT, ZENUSDT, ZILUSDT, ZKUSDT, ZROUSDT, ZRXUSDT

First snapshot: BTCUSDT, ETHUSDT, BNBUSDT, XRPUSDT, EOSUSDT, LTCUSDT, TRXUSDT, LINKUSDT, MATICUSDT, VETUSDT, ADAUSDT, ETCUSDT, ONTUSDT, NEOUSDT, XLMUSDT, BTTUSDT, BCHUSDT, ATOMUSDT, FETUSDT, IOSTUSDT, QTUMUSDT, XTZUSDT, KAVAUSDT, XMRUSDT, TOMOUSDT, ALGOUSDT, BATUSDT, TROYUSDT, ZECUSDT, DASHUSDT, DOCKUSDT, WAVESUSDT, IOTAUSDT, RVNUSDT, ONEUSDT, ERDUSDT, ZRXUSDT, CHZUSDT, ENJUSDT, HOTUSDT, STXUSDT, NPXSUSDT, NKNUSDT, ICXUSDT, ZILUSDT, COCOSUSDT~20210119, ARPAUSDT, BEAMUSDT, MCOUSDT, CELRUSDT

## 5. Excluded pairs

- **leveraged token** (50): 1INCHDOWNUSDT, 1INCHUPUSDT, AAVEDOWNUSDT, AAVEUPUSDT, ADADOWNUSDT, ADAUPUSDT, BCHDOWNUSDT, BCHUPUSDT, BEARUSDT, BNBBEARUSDT, BNBBULLUSDT, BNBDOWNUSDT, BNBUPUSDT, BTCDOWNUSDT, BTCUPUSDT, BULLUSDT, DOTDOWNUSDT, DOTUPUSDT, EOSBEARUSDT, EOSBULLUSDT, EOSDOWNUSDT, EOSUPUSDT, ETHBEARUSDT, ETHBULLUSDT, ETHDOWNUSDT, ETHUPUSDT, FILDOWNUSDT, FILUPUSDT, LINKDOWNUSDT, LINKUPUSDT, LTCDOWNUSDT, LTCUPUSDT, SUSHIDOWNUSDT, SUSHIUPUSDT, SXPDOWNUSDT, SXPUPUSDT, TRXDOWNUSDT, TRXUPUSDT, UNIDOWNUSDT, UNIUPUSDT, XLMDOWNUSDT, XLMUPUSDT, XRPBEARUSDT, XRPBULLUSDT, XRPDOWNUSDT, XRPUPUSDT, XTZDOWNUSDT, XTZUPUSDT, YFIDOWNUSDT, YFIUPUSDT
- **meme coin** (32): 1000CATUSDT, 1000CHEEMSUSDT, 1000SATSUSDT, 1MBABYDOGEUSDT, ACTUSDT, BANANAS31USDT, BOMEUSDT, BONKUSDT, BROCCOLI714USDT, CATIUSDT, DOGEUSDT, DOGSUSDT, FLOKIUSDT, GIGGLEUSDT, HMSTRUSDT, LUNCUSDT, MEMEUSDT, MUBARAKUSDT, NEIROUSDT, NOTUSDT, PENGUUSDT, PEOPLEUSDT, PEPEUSDT, PNUTUSDT, PUMPUSDT, SHIBUSDT, TRUMPUSDT, TSTUSDT, TURBOUSDT, TUTUSDT, WIFUSDT, 币安人生USDT
- **sharia screen (lending/gambling)** (9): AAVEUSDT, ALPACAUSDT, COMPUSDT, CREAMUSDT, FUNUSDT, JSTUSDT, MORPHOUSDT, WINUSDT, XVSUSDT
- **stablecoin** (27): AEURUSDT, AUDUSDT, BFUSDUSDT, BKRWUSDT, BUSDUSDT, DAIUSDT, EURIUSDT, EURUSDT, FDUSDUSDT, FRAXUSDT, GBPUSDT, KGSTUSDT, PAXUSDT, RLUSDUSDT, SUSDUSDT, TUSDUSDT, USD1USDT, USDCUSDT, USDEUSDT, USDPUSDT, USDSBUSDT, USDSOLDUSDT, USDSUSDT, USTCUSDT, USTUSDT, UUSDT, XUSDUSDT
- **tokenized stock/ETF** (68): AAOIBUSDT, AAPLBUSDT, ALABBUSDT, AMATBUSDT, AMDBUSDT, AMZNBUSDT, ARMBUSDT, ASMLBUSDT, ASTSBUSDT, AVGOBUSDT, AXTIBUSDT, BABABUSDT, BEBUSDT, BMNRBUSDT, CBRSBUSDT, COHRBUSDT, COINBUSDT, CRCLBUSDT, CRDOBUSDT, CRWVBUSDT, DELLBUSDT, DJTBUSDT, DRAMBUSDT, EWYBUSDT, FLNCBUSDT, GLWBUSDT, GMEBUSDT, GOOGLBUSDT, GSBUSDT, HOODBUSDT, IBMBUSDT, INTCBUSDT, INTWBUSDT, IRENBUSDT, KORUBUSDT, LITEBUSDT, METABUSDT, MRVLBUSDT, MSFTBUSDT, MSTRBUSDT, MUBUSDT, MUUBUSDT, MVLLBUSDT, NBISBUSDT, NFLXBUSDT, NOKBUSDT, NVDABUSDT, ORCLBUSDT, PLTRBUSDT, PYPLBUSDT, QCOMBUSDT, QNTBUSDT, QQQBUSDT, RKLBBUSDT, SKHYBUSDT, SMCIBUSDT, SMHBUSDT, SNDKBUSDT, SNXXBUSDT, SOXLBUSDT, SOXSBUSDT, SPCXBUSDT, SPYBUSDT, TQQQBUSDT, TSLABUSDT, TSMBUSDT, USARBUSDT, WDCBUSDT
- **wrapped/backed asset** (6): BETHUSDT, BNSOLUSDT, PAXGUSDT, WBETHUSDT, WBTCUSDT, XAUTUSDT

## 6. Caveats

- **Survivorship bias** is addressed with the point-in-time universe above. Coins delisted while a position was open are closed at their last traded price.
- Token redenominations / relaunches (e.g. COCOS x1000, LUNA → LUNA 2.0, QUICK /1000) are split into separate assets (`SYMBOL~YYYYMMDD` = the old token, ending that day); no trade spans the swap.
- Profit factor and max drawdown are in dollars on a compounding account, so a losing streak early (e.g. 2022) weighs more than later wins; expectancy in R is the size-independent measure.
- Flash-crash wicks (e.g. 10 Oct 2025) fill stops at the stop price; real fills would have been worse.
- Intrabar order is unknown on OHLC bars; when a bar touches both stop and target the stop is assumed first (conservative). Gaps through a level fill at the open.
- When cash runs short, simultaneous signals are filled in alphabetical order.
- Past performance, even out-of-sample, does not guarantee future results. Paper-trade before going live.
