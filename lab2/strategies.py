"""Benchmarks B1/B2 and strategies S1-S7. Parameter grids are fixed here, up front.

Every `step(d, acct, prices)` call may only read signals as of the previous day's close
(`self.sig(series, d)` looks up d - 1 day); trades execute at day d's open.

Frame A (lump sum $10,000): DCA-style strategies (S2-S5) use a base weekly amount of
$10,000 / 104 (a 2-year deployment plan at x1) drawn from the lump-sum cash.
Frame B ($100 every Monday): the base amount is the $100 contribution; unspent money
stays in a 0%-interest cash reserve that later multipliers can spend.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import signals as sg
from .sim import FEE, LUMP_SUM, SLIP, WEEKLY

BTC, ETH = "BTCUSDT", "ETHUSDT"
DAY = pd.Timedelta(days=1)
BASE_A = LUMP_SUM / 104
TRIM_COOLDOWN_WEEKS = 4


class Context:
    """Everything strategies may read: price signals, on-chain inputs, alt universe."""

    def __init__(self, sig_price: pd.Series, mvrv: pd.DataFrame | None = None, alt_close: pd.DataFrame | None = None,
                 universe=None, eth: pd.DataFrame | None = None, btc: pd.DataFrame | None = None):
        self.sig_price = sig_price
        self.mvrv = mvrv
        self.alt_close = alt_close
        self.universe = universe
        self.eth = eth
        self.btc = btc


class Strategy:
    key = "?"
    name = "?"

    def __init__(self, ctx: Context, **params):
        self.ctx = ctx
        self.params = params
        self.prepare()

    def prepare(self):
        pass

    def reset(self, frame: str):
        self.frame = frame
        self.base = WEEKLY if frame == "B" else BASE_A
        self.started = False
        self.last_trim = None

    @staticmethod
    def sig(series: pd.Series, d):
        """Signal value as of the close of the day before d (no look-ahead)."""
        v = series.asof(d - DAY) if len(series) else np.nan
        return v

    def label(self) -> str:
        return ", ".join(f"{k}={v}" for k, v in self.params.items()) or "-"

    def step(self, d, acct, prices):
        raise NotImplementedError

    # helpers
    def trim_ok(self, d) -> bool:
        return self.last_trim is None or (d - self.last_trim).days >= 7 * TRIM_COOLDOWN_WEEKS

    def trim(self, d, acct, price, frac):
        if acct.qty.get(BTC, 0) > 0 and self.trim_ok(d):
            acct.sell(BTC, acct.qty[BTC] * frac, price)
            self.last_trim = d


# ----------------------------------------------------------------------------- benchmarks
class BuyHold(Strategy):
    key, name = "B1", "BTC buy & hold"

    def step(self, d, acct, prices):
        if acct.cash > 1 and (not self.started or (self.frame == "B" and d.dayofweek == 0)):
            acct.buy(BTC, acct.cash, prices.open.at[d, BTC])
            self.started = True


class PlainDCA(Strategy):
    key, name = "B2", "Weekly DCA into BTC"

    def step(self, d, acct, prices):
        if d.dayofweek == 0:
            acct.buy(BTC, self.base, prices.open.at[d, BTC])


# ----------------------------------------------------------------------------- S1
class RegimeFilter(Strategy):
    """S1: hold BTC while close > SMA (checked daily, traded on Mondays), else cash."""
    key, name = "S1", "BTC regime filter"
    GRID = {"sma": ["20w", "200d", "50w"]}  # ordered by length: 140d < 200d < 350d

    def prepare(self):
        self.up = sg.regime_up(self.ctx.sig_price, self.params["sma"])

    def step(self, d, acct, prices):
        if d.dayofweek != 0:
            return
        up = self.sig(self.up, d)
        px = prices.open.at[d, BTC]
        if up == True:  # noqa: E712  (NaN during warm-up -> stay in cash)
            acct.buy(BTC, acct.cash, px)
        elif acct.qty.get(BTC, 0) > 0:
            acct.sell(BTC, acct.qty[BTC], px)


# ----------------------------------------------------------------------------- DCA family
class _WeeklyDCA(Strategy):
    def multiplier(self, d) -> float:
        raise NotImplementedError

    def extra(self, d, acct, mult) -> float:
        return 0.0

    def maybe_trim(self, d, acct, px):
        pass

    def step(self, d, acct, prices):
        if d.dayofweek != 0:
            return
        px = prices.open.at[d, BTC]
        self.maybe_trim(d, acct, px)
        mult = self.multiplier(d)
        if not np.isfinite(mult):
            mult = 1.0  # signal not available yet -> plain DCA
        acct.buy(BTC, self.base * mult + self.extra(d, acct, mult), px)


S2_TABLES = {
    # (upper bound of price / 200w SMA, multiplier) ..., trim level, trim fraction
    "mild": ([(1.0, 2.0), (2.0, 1.0), (3.0, 0.75), (np.inf, 0.25)], 4.0, 0.10),
    "base": ([(1.0, 3.0), (2.0, 1.0), (3.0, 0.5), (np.inf, 0.0)], 4.0, 0.10),
    "aggressive": ([(1.5, 3.0), (2.5, 1.0), (3.5, 0.25), (np.inf, 0.0)], 3.5, 0.10),
}


class DCA200W(_WeeklyDCA):
    """S2: weekly buy = base x multiplier from price / 200-week SMA; trim 10% when very extended."""
    key, name = "S2", "DCA vs 200-week SMA"
    GRID = {"table": ["mild", "base", "aggressive"]}

    def prepare(self):
        self.ratio = sg.ratio_to_200w(self.ctx.sig_price)
        self.table, self.trim_at, self.trim_frac = S2_TABLES[self.params["table"]]

    def multiplier(self, d):
        r = self.sig(self.ratio, d)
        if not np.isfinite(r):
            return np.nan
        return next(m for ub, m in self.table if r < ub)

    def maybe_trim(self, d, acct, px):
        r = self.sig(self.ratio, d)
        if np.isfinite(r) and r > self.trim_at:
            self.trim(d, acct, px, self.trim_frac)


class DrawdownDCA(Strategy):
    """S3: buy only when BTC is >= X below its expanding ATH; otherwise save the $100.
    When triggered, the reserve saved before the episode is deployed over N weeks."""
    key, name = "S3", "Drawdown-from-ATH DCA"
    GRID = {"x": [0.30, 0.40, 0.50], "n_weeks": [4, 12]}

    def prepare(self):
        self.dd = sg.drawdown_from_ath(self.ctx.sig_price)

    def reset(self, frame):
        super().reset(frame)
        self.base = WEEKLY if frame == "B" else 0.0  # frame A: the lump sum is the reserve
        self.in_episode = False
        self.deploy = 0.0

    def step(self, d, acct, prices):
        if d.dayofweek != 0:
            return
        dd = self.sig(self.dd, d)
        if not (np.isfinite(dd) and dd >= self.params["x"]):
            self.in_episode = False
            return  # contribution stays in the reserve
        if not self.in_episode:
            self.in_episode = True
            self.deploy = max(acct.cash - self.base, 0.0) / self.params["n_weeks"]
        acct.buy(BTC, self.base + self.deploy, prices.open.at[d, BTC])


class LogRegBand(_WeeklyDCA):
    """S4: log10(price) ~ log10(days since genesis), expanding fit refit monthly.
    x2 below the midline (and redeploy 1/4 of the reserve), x1 up to +1 sigma, x0 above;
    trim 15% of holdings above +trim_z sigma (spec: 2.0)."""
    key, name = "S4", "Log-regression band"
    GRID = {"trim_z": [1.5, 2.0, 2.5]}

    def prepare(self):
        self.z = sg.logreg_z(self.ctx.sig_price)

    def multiplier(self, d):
        z = self.sig(self.z, d)
        if not np.isfinite(z):
            return np.nan
        return 2.0 if z < 0 else (1.0 if z < 1 else 0.0)

    def extra(self, d, acct, mult):
        z = self.sig(self.z, d)
        if np.isfinite(z) and z < 0:
            return max(acct.cash - self.base * mult, 0.0) / 4
        return 0.0

    def maybe_trim(self, d, acct, px):
        z = self.sig(self.z, d)
        if np.isfinite(z) and z > self.params["trim_z"]:
            self.trim(d, acct, px, 0.15)


class MVRVZ(_WeeklyDCA):
    """S5: x2 when MVRV-Z < 0, x1 otherwise; trim 15% of holdings when MVRV-Z > K."""
    key, name = "S5", "MVRV-Z DCA"
    GRID = {"k": [5, 6, 7]}

    def prepare(self):
        self.z = sg.mvrv_z(self.ctx.mvrv)

    def multiplier(self, d):
        z = self.sig(self.z, d)
        if not np.isfinite(z):
            return np.nan
        return 2.0 if z < 0 else 1.0

    def maybe_trim(self, d, acct, px):
        z = self.sig(self.z, d)
        if np.isfinite(z) and z > self.params["k"]:
            self.trim(d, acct, px, 0.15)


# ----------------------------------------------------------------------------- S6
class AltRotation(Strategy):
    """S6: when BTC > 200d SMA hold the top-N alts of the point-in-time halal top 50 by
    4-week return (equal weight, weekly rebalance); otherwise 100% BTC or cash.
    core > 0 gives the core-satellite variant: `core` in S1-BTC (200d), the rest in the rotation."""
    key, name = "S6", "Alt momentum rotation"
    GRID = {"n": [3, 5], "off": ["btc", "cash"]}

    def prepare(self):
        self.up = sg.regime_up(self.ctx.sig_price, "200d")
        self.mom = sg.momentum(self.ctx.alt_close, 28)
        self.core = self.params.get("core", 0.0)

    def picks(self, d) -> list[str]:
        prev = d - DAY
        month_start = prev.normalize().replace(day=1)
        names = [s for s in self.ctx.universe(month_start) if s != BTC]
        if not names:
            return []
        row = self.mom.loc[:prev].iloc[-1] if len(self.mom.loc[:prev]) else None
        if row is None:
            return []
        m = row.reindex(names).dropna()
        return list(m.sort_values(ascending=False).index[: self.params["n"]])

    def step(self, d, acct, prices):
        if d.dayofweek != 0:
            return
        up = self.sig(self.up, d) == True  # noqa: E712
        opens = prices.open.loc[d]
        weights = {}
        if up:
            alts = [s for s in self.picks(d) if np.isfinite(opens.get(s, np.nan))]
            if self.core:
                weights[BTC] = self.core
            for s in alts:
                weights[s] = (1 - self.core) / len(alts)
        elif self.params["off"] == "btc":
            weights[BTC] = 1 - self.core if self.core else 1.0
        px = {s: opens[s] if np.isfinite(opens.get(s, np.nan)) else prices.last_close.at[d, s]
              for s in set(weights) | set(acct.qty)}
        acct.rebalance(weights, px)


class CoreSatellite(AltRotation):
    key, name = "S6cs", "Core-satellite 85% S1-BTC / 15% rotation"
    GRID = {"n": [3, 5], "off": ["btc", "cash"]}

    def __init__(self, ctx, **params):
        super().__init__(ctx, core=0.85, **params)

    def label(self):
        return ", ".join(f"{k}={v}" for k, v in self.params.items() if k != "core")


# ----------------------------------------------------------------------------- S7
class FibPullback(Strategy):
    """S7: BTC/ETH 61.8% pullback of the last ZigZag up-swing, only while BTC > 200d SMA.
    Entry limit at 61.8%, stop just below 78.6%, target = prior swing high.
    Risk 1.5% of equity per trade, one position per asset, max 3 entries per day."""
    key, name = "S7", "BTC/ETH Fibonacci 61.8% pullback"
    GRID = {"zigzag": [0.10, 0.15]}
    RISK = 0.015
    MAX_ENTRIES_PER_DAY = 3

    def prepare(self):
        self.up = sg.regime_up(self.ctx.sig_price, "200d")
        self.setups = {}
        for sym, df in ((BTC, self.ctx.btc), (ETH, self.ctx.eth)):
            piv = sg.zigzag(df["high"], df["low"], self.params["zigzag"])
            self.setups[sym] = sg.fib_setups(piv)

    def reset(self, frame):
        super().reset(frame)
        self.pos = {}
        self.used = set()
        self.prev_equity = None

    def step(self, d, acct, prices):
        o, h, l = prices.open.loc[d], prices.high.loc[d], prices.low.loc[d]
        # exits first
        for sym in list(self.pos):
            p = self.pos[sym]
            if l[sym] <= p["stop"]:
                self._exit(d, acct, sym, min(o[sym], p["stop"]), "stop")
            elif h[sym] >= p["target"]:
                self._exit(d, acct, sym, max(o[sym], p["target"]), "target")
        equity = self.prev_equity if self.prev_equity is not None else acct.value(
            {s: o[s] for s in acct.qty})
        entries = 0
        if self.sig(self.up, d) == True:  # noqa: E712
            for sym, st in self.setups.items():
                if sym in self.pos or entries >= self.MAX_ENTRIES_PER_DAY or not np.isfinite(o[sym]):
                    continue
                live = st[(st["live_from"] < d) & (st["expires"] >= d)]
                if live.empty:
                    continue
                k = live.index[-1]
                if (sym, k) in self.used:
                    continue
                s = live.loc[k]
                if o[sym] <= s["stop"]:
                    self.used.add((sym, k))  # gapped through the stop before we could buy
                    continue
                if l[sym] <= s["entry"]:
                    fill = min(o[sym], s["entry"])
                    buy_px = fill * (1 + SLIP) * (1 + FEE)
                    per_unit = buy_px - s["stop"] * (1 - SLIP) * (1 - FEE)  # loss per unit at the stop
                    cash_before = acct.cash
                    q = acct.buy(sym, self.RISK * equity / per_unit * buy_px, fill)
                    self.used.add((sym, k))
                    if q > 0:
                        entries += 1
                        self.pos[sym] = {"qty": q, "entry": fill, "stop": s["stop"], "target": s["target"],
                                         "date": d, "cost": cash_before - acct.cash, "per_unit": per_unit}
                        if l[sym] <= s["stop"]:  # same-bar stop (conservative)
                            self._exit(d, acct, sym, s["stop"], "stop")
        closes = prices.last_close.loc[d]
        self.prev_equity = acct.value({s: closes[s] for s in acct.qty})

    def _exit(self, d, acct, sym, price, reason):
        p = self.pos.pop(sym)
        q = min(p["qty"], acct.qty.get(sym, 0.0))
        usd = acct.sell(sym, q, price)
        risk = q * p["per_unit"]
        acct.trades.append({"asset": sym, "entry_date": p["date"], "exit_date": d, "entry": p["entry"],
                            "exit": price, "reason": reason, "pnl": usd - p["cost"],
                            "r": (usd - p["cost"]) / risk if risk > 0 else np.nan})


STRATEGIES = [RegimeFilter, DCA200W, DrawdownDCA, LogRegBand, MVRVZ, AltRotation, CoreSatellite, FibPullback]
BENCHMARKS = [BuyHold, PlainDCA]
