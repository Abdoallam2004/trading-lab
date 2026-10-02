"""Phase A: write reports/lab4_data_inventory.md from the cached data (first/last date, rows, largest gap)."""
import pandas as pd

import _bootstrap  # noqa: F401
from lab.config import REPORTS_DIR
from lab4.data import LAB4_DIR, load

SOURCES = {
    "spot": "Binance spot klines incl. taker-buy volume — data.binance.vision (S3 mirror) `data/spot/{monthly,daily}/klines`",
    "funding": "Binance USD-M funding rate — `data/futures/um/{monthly,daily}/fundingRate`",
    "premium": "Binance USD-M premium-index klines — `data/futures/um/monthly/premiumIndexKlines`",
    "metrics": "Binance USD-M daily metrics (5-min open interest, top-trader & global long/short ratios, "
               "taker buy/sell volume ratio) — `data/futures/um/daily/metrics`",
    "vix": "CBOE VIX daily, via github.com/datasets/finance-vix (raw.githubusercontent.com)",
    "us10y": "US 10-year yield, MONTHLY only, via github.com/datasets/bond-yields-us-10y",
}
EXPECTED = {"1h": "1h", "4h": "4h", "1d": "1D", "funding": "8h", "metrics": "5min", "vix": "1D", "us10y": "MS"}


def describe(name):
    df = load(name)
    idx = df.index.sort_values()
    gaps = idx.to_series().diff().dropna()
    kind = name.split("_")[0]
    freq = next((v for k, v in EXPECTED.items() if name.endswith(k) or name.startswith(k)), "?")
    step = pd.Timedelta(freq) if freq not in ("MS",) else pd.Timedelta(days=31)
    big = gaps[gaps > step * 1.5]
    worst = f"{big.max()} (ending {big.idxmax():%Y-%m-%d %H:%M})" if len(big) else "none"
    return [f"`{name}`", SOURCES.get(kind, kind), f"{idx[0]:%Y-%m-%d}", f"{idx[-1]:%Y-%m-%d}", freq, len(df),
            len(big), worst]


rows = [describe(p.stem) for p in sorted(LAB4_DIR.glob("*.parquet"))]
L = ["# Lab 4 — data inventory\n",
     "Everything below was downloaded by `scripts/lab4_download.py` into `data/lab4/` (not committed). "
     "'Gaps' counts intervals longer than 1.5× the nominal step (weekends/holidays for VIX and the 10y series are "
     "expected; for 24/7 crypto series they are exchange outages or archive holes).\n",
     "## Available\n",
     "| Dataset | Source | First | Last | Step | Rows | Gaps | Largest gap |",
     "|---|---|---|---|---|---|---|---|"]
L += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
L += ["",
      "Proxies used where the requested series is unavailable (labelled as proxies everywhere they are used):",
      "- **Gold → `spot_PAXGUSDT_1d`** (Binance PAXG/USDT, a token redeemable for 1 troy oz; from 2020-08-28).",
      "- **Dollar index (DXY) → inverse of `spot_EURUSDT_1d`** (EUR is ~57.6% of DXY; from 2020-01-03).",
      "",
      "## Not available (skipped, never fabricated)\n",
      "| Requested | Why | Effect |",
      "|---|---|---|",
      "| Crypto Fear & Greed history (alternative.me) | host blocked by this environment's network policy | D7 and the "
      "F&G part of L3 are skipped; the daily logger records F&G going forward where the host is reachable |",
      "| FRED: DGS10 daily, DFF, WALCL, DTWEXBGS | fred.stlouisfed.org and api.stlouisfed.org blocked; only a "
      "MONTHLY 10y series is reachable (DataHub) | no daily 10y, Fed funds or Fed balance-sheet correlations; DXY "
      "replaced by the EUR/USDT proxy |",
      "| Nasdaq-100 / QQQ daily | stooq, Yahoo, Alpha Vantage, FMP hosts blocked; no free mirror reachable | no "
      "Nasdaq correlation or Nasdaq-based macro regime; the macro regime uses VIX and the dollar proxy instead |",
      "| Gold spot daily (LBMA) | no reachable daily source (DataHub has monthly only) | PAXG/USDT proxy |",
      "| FOMC meeting dates, US CPI release dates | federalreserve.gov and bls.gov blocked | D-3 event windows and "
      "the D-4 calendar filter are skipped (typing the dates from memory would risk fabricated data) |",
      "| US spot BTC ETF daily net flows | farside.co.uk blocked; no other free source with clear terms | skipped |",
      "| Liquidation history | Binance's `liquidationSnapshot` archive is empty for BTCUSDT/ETHUSDT; the live "
      "force-order endpoint needs an API key | liquidations are proxied by open-interest drops (D3); S-c "
      "stops (below liquidation clusters) cannot be tested |",
      "| Token-unlock history | no free historical source | L4 skipped; see Phase F |",
      "",
      "## How the user can unblock the missing sources",
      "Allow these hosts in the environment's network settings and re-run `scripts/lab4_download.py` (and extend it): "
      "`api.alternative.me`, `fred.stlouisfed.org`, `stooq.com`, `www.federalreserve.gov`, `www.bls.gov`, "
      "`fapi.binance.com` (live futures endpoints for the logger).",
      ""]
(REPORTS_DIR / "lab4_data_inventory.md").write_text("\n".join(L))
print("\n".join(L[:20]))
