"""Daily spot-only portfolio simulator for Lab 2.

Timing: a strategy decides with information up to the close of day t-1 and trades at the
open of day t (weekly strategies: Sunday close -> Monday open). Contributions (frame B)
arrive on Monday before trading. Every fill pays 0.10% fee + 0.05% slippage. Cash earns 0%.
No leverage: buys are capped at available cash; no shorting: sells capped at holdings.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

FEE = 0.001
SLIP = 0.0005
LUMP_SUM = 10_000.0
WEEKLY = 100.0
MIN_TRADE = 1.0  # USD


class Prices:
    """Aligned daily open/high/low/close per asset on one calendar index."""

    def __init__(self, frames: dict[str, pd.DataFrame]):
        idx = None
        for df in frames.values():
            idx = df.index if idx is None else idx.union(df.index)
        self.index = idx
        self.open = pd.DataFrame({s: d["open"] for s, d in frames.items()}).reindex(idx)
        self.high = pd.DataFrame({s: d["high"] for s, d in frames.items()}).reindex(idx)
        self.low = pd.DataFrame({s: d["low"] for s, d in frames.items()}).reindex(idx)
        self.close = pd.DataFrame({s: d["close"] for s, d in frames.items()}).reindex(idx)
        self.last_close = self.close.ffill()


@dataclass
class Account:
    cash: float = 0.0
    qty: dict = field(default_factory=dict)
    contributed: float = 0.0
    traded: float = 0.0
    n_trades: int = 0
    flows: list = field(default_factory=list)   # (date, amount) money added by the investor
    trades: list = field(default_factory=list)  # closed round trips (S7)

    def deposit(self, d, amount: float):
        self.cash += amount
        self.contributed += amount
        self.flows.append((d, amount))

    def buy(self, sym: str, usd: float, price: float) -> float:
        """Spend up to `usd` (fee included). Returns quantity bought."""
        usd = min(usd, self.cash)
        if usd < MIN_TRADE or not np.isfinite(price) or price <= 0:
            return 0.0
        fill = price * (1 + SLIP)
        q = usd / (1 + FEE) / fill
        self.cash -= usd
        self.qty[sym] = self.qty.get(sym, 0.0) + q
        self.traded += usd
        self.n_trades += 1
        return q

    def sell(self, sym: str, q: float, price: float) -> float:
        """Sell up to `q` units. Returns USD received."""
        q = min(q, self.qty.get(sym, 0.0))
        if q <= 0 or not np.isfinite(price) or price <= 0:
            return 0.0
        fill = price * (1 - SLIP)
        usd = q * fill * (1 - FEE)
        if q * fill < MIN_TRADE and q < self.qty.get(sym, 0.0):
            return 0.0
        self.qty[sym] -= q
        if self.qty[sym] <= 1e-15:
            del self.qty[sym]
        self.cash += usd
        self.traded += q * fill
        self.n_trades += 1
        return usd

    def value(self, prices: dict) -> float:
        return self.cash + sum(q * prices[s] for s, q in self.qty.items())

    def rebalance(self, weights: dict, prices: dict, min_frac: float = 0.01):
        """Trade to target weights of total equity (sells first). Skips drifts < min_frac of equity."""
        eq = self.value(prices)
        if eq <= 0:
            return
        for s in list(self.qty):
            target = weights.get(s, 0.0) * eq
            cur = self.qty[s] * prices[s]
            if cur - target > max(min_frac * eq, MIN_TRADE) or (target == 0 and cur > 0):
                self.sell(s, (cur - target) / prices[s] if target > 0 else self.qty[s], prices[s])
        for s, w in weights.items():
            cur = self.qty.get(s, 0.0) * prices[s]
            if w * eq - cur > max(min_frac * eq, MIN_TRADE):
                self.buy(s, w * eq - cur, prices[s])


@dataclass
class RunResult:
    equity: pd.Series          # end-of-day portfolio value
    crypto: pd.Series          # end-of-day value held in crypto
    btc_qty: pd.Series         # end-of-day BTC units held
    flows: pd.Series           # investor money added per day
    contributed: float
    n_trades: int
    traded: float
    trades: list
    cash: pd.Series | None = None  # end-of-day cash


def utc(x) -> pd.Timestamp:
    x = pd.Timestamp(x)
    return x.tz_localize("UTC") if x.tz is None else x.tz_convert("UTC")


def run(strategy, prices: Prices, start, end, frame: str) -> RunResult:
    """Simulate `strategy` from `start` to `end` (inclusive) in frame 'A' (lump sum) or 'B' (weekly)."""
    days = prices.index[(prices.index >= utc(start)) & (prices.index <= utc(end))]
    acct = Account()
    strategy.reset(frame)
    eq, cr, bq, ca = (np.empty(len(days)) for _ in range(4))
    flows = np.zeros(len(days))
    for k, d in enumerate(days):
        if frame == "A" and k == 0:
            acct.deposit(d, LUMP_SUM)
            flows[k] += LUMP_SUM
        if frame == "B" and d.dayofweek == 0:
            acct.deposit(d, WEEKLY)
            flows[k] += WEEKLY
        # assets that stopped trading (delisted) are sold at their last close
        for s in list(acct.qty):
            if np.isnan(prices.open.at[d, s]):
                acct.sell(s, acct.qty[s], prices.last_close.at[d, s])
        strategy.step(d, acct, prices)
        closes = prices.last_close.loc[d]
        held = {s: closes[s] for s in acct.qty}
        cr[k] = sum(q * held[s] for s, q in acct.qty.items())
        eq[k] = acct.cash + cr[k]
        bq[k] = acct.qty.get("BTCUSDT", 0.0)
        ca[k] = acct.cash
    return RunResult(pd.Series(eq, days), pd.Series(cr, days), pd.Series(bq, days), pd.Series(flows, days),
                     acct.contributed, acct.n_trades, acct.traded, acct.trades, pd.Series(ca, days))


# ----------------------------------------------------------------------------- metrics
def twr_returns(r: RunResult) -> pd.Series:
    """Daily time-weighted returns (investor flows removed)."""
    v, f = r.equity, r.flows
    prev = v.shift(1)
    ret = (v - f) / prev - 1
    ret.iloc[0] = v.iloc[0] / f.iloc[0] - 1 if f.iloc[0] > 0 else 0.0
    return ret.where(prev > 0, 0.0).fillna(0.0)


def max_drawdown(index: pd.Series) -> float:
    if len(index) == 0:
        return 0.0
    return float((1 - index / index.cummax()).max())


def irr(r: RunResult) -> float:
    """Money-weighted annual return (XIRR) of the investor's flows and the final value."""
    t = ((r.flows.index - r.flows.index[0]) / pd.Timedelta(days=365.25)).to_numpy()
    cf = -r.flows.to_numpy()
    cf[-1] += r.equity.iloc[-1]
    mask = cf != 0
    t, cf = t[mask], cf[mask]

    def npv(x):
        return float(np.sum(cf / (1 + x) ** t))
    lo, hi = -0.99, 20.0
    if npv(lo) * npv(hi) > 0:
        return np.nan
    for _ in range(200):  # bisection; npv is monotonic for an investor's out-then-in flows
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def metrics(r: RunResult, frame: str) -> dict:
    ret = twr_returns(r)
    nav = (1 + ret).cumprod()
    years = max((r.equity.index[-1] - r.equity.index[0]).days / 365.25, 1 / 365.25)
    twr_cagr = nav.iloc[-1] ** (1 / years) - 1
    dd = max_drawdown(nav)
    sd = ret.std()
    final = float(r.equity.iloc[-1])
    btc_end = float(r.btc_qty.iloc[-1])
    expo = (r.crypto / r.equity.replace(0, np.nan)).fillna(0.0)
    avg_eq = float(r.equity[r.equity > 0].mean()) if (r.equity > 0).any() else np.nan
    return {
        "final": final,
        "contributed": r.contributed,
        "multiple": final / r.contributed if r.contributed else np.nan,
        "cagr": (final / r.contributed) ** (1 / years) - 1 if frame == "A" else twr_cagr,
        "irr": irr(r) if frame == "B" else (final / r.contributed) ** (1 / years) - 1,
        "max_dd": dd,
        "calmar": twr_cagr / dd if dd > 0 else np.nan,
        "sharpe": float(ret.mean() / sd * np.sqrt(365)) if sd > 0 else np.nan,
        "btc_per_1k": btc_end / r.contributed * 1000 if r.contributed else np.nan,
        "exposure": float(expo.mean()),
        "time_in_market": float((expo > 0.05).mean()),
        "trades": r.n_trades,
        "turnover": r.traded / avg_eq / years if avg_eq and avg_eq > 0 else np.nan,
    }
