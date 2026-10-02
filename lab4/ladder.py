"""Phase E: spot ladder (grid) accumulation on BTC 1h bars, plus overlay strategies for L3.

L1 rules: capital C, lot = C / N (fixed dollars). At the start (and whenever no lot is open) one lot is
bought at the bar's open. Then a buy limit sits g% below the most recent fill (= the cheapest open lot)
while fewer than N lots are open and cash allows. Every lot has its own sell limit at cost x (1 + tp),
tp in {g, 2g}; a lot is never sold at a loss. Limits fill only on trade-through (0.02%), at the user's
0.075% fee, no slippage. A lot bought on a bar cannot also be sold on that bar.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from lab2.strategies import DCA200W

from .data import load
from .phaseC import daily_inputs
from lab3.partA import expanding_percentile

FEE = 0.00075
TT = 0.0002
L1_GRID = [{"g": g, "n": n, "tp": tp} for g in (0.03, 0.05, 0.08) for n in (5, 10) for tp in ("g", "2g")]
L2_LADDER = {"g": 0.05, "n": 10, "tp": "g"}     # declared before running, not selected


class Hourly:
    def __init__(self):
        d = load("spot_BTCUSDT_1h")
        d = d[~d.index.duplicated()].sort_index()
        self.index = d.index
        self.o, self.h, self.l, self.c = (d[x].to_numpy(float) for x in ("open", "high", "low", "close"))


def ladder(hb: Hourly, start, end, g: float, n: int, tp: str, capital: float = 10_000.0) -> dict:
    """Run L1 between start and end (inclusive days). Returns metrics + the daily equity curve."""
    a = int(hb.index.searchsorted(pd.Timestamp(start)))
    z = int(hb.index.searchsorted(pd.Timestamp(end) + pd.Timedelta(days=1))) - 1
    tpv = g if tp == "g" else 2 * g
    lot_usd = capital / n
    cash = capital
    lots: list[list] = []                # [cost_price, qty, bought_idx]
    qty_path = np.zeros(z - a + 1)
    cash_path = np.zeros(z - a + 1)
    round_trips, longest = 0, 0
    j = a
    last_mark = a

    def mark(upto):
        nonlocal last_mark
        q = sum(l[1] for l in lots)
        qty_path[last_mark - a:upto - a] = q
        cash_path[last_mark - a:upto - a] = cash
        last_mark = upto

    while j <= z:
        if not lots and cash >= lot_usd * 0.999:
            mark(j)
            px = hb.o[j]
            q = lot_usd / (px * (1 + FEE))
            cash -= lot_usd
            lots.append([px, q, j])
        buy_lvl = min(l[0] for l in lots) * (1 - g) if (lots and len(lots) < n and cash >= lot_usd * 0.999) else -np.inf
        sell_lvl = min(l[0] for l in lots) * (1 + tpv) if lots else np.inf
        # jump to the next bar where a buy or a sell limit can trade through
        k0, chunk, k = j + 1, 256, -1
        while k0 <= z:
            k1 = min(z, k0 + chunk - 1)
            m = (hb.l[k0:k1 + 1] <= buy_lvl * (1 - TT)) | (hb.h[k0:k1 + 1] >= sell_lvl * (1 + TT))
            if m.any():
                k = k0 + int(np.argmax(m))
                break
            k0, chunk = k1 + 1, chunk * 2
        if k < 0:
            break
        mark(k)
        # sells of lots bought before this bar
        for lot in sorted(lots, key=lambda x: x[0]):
            tgt = lot[0] * (1 + tpv)
            if lot[2] < k and hb.h[k] >= tgt * (1 + TT):
                cash += lot[1] * max(hb.o[k], tgt) * (1 - FEE)
                longest = max(longest, k - lot[2])
                lots.remove(lot)
                round_trips += 1
        # buys (possibly several levels on a big drop)
        while lots and len(lots) < n and cash >= lot_usd * 0.999:
            lvl = min(l[0] for l in lots) * (1 - g)
            if hb.l[k] > lvl * (1 - TT):
                break
            px = min(hb.o[k], lvl)
            cash -= lot_usd
            lots.append([px, lot_usd / (px * (1 + FEE)), k])
        j = k
    mark(z + 1)
    for lot in lots:
        longest = max(longest, z - lot[2])
    idx = hb.index[a:z + 1]
    eq = pd.Series(cash_path + qty_path * hb.c[a:z + 1], index=idx)
    daily = eq.resample("1D").last().dropna()
    invested = pd.Series(qty_path * hb.c[a:z + 1], index=idx).resample("1D").last().dropna()
    peak = np.maximum(daily.cummax(), capital)   # drawdown measured from the starting capital too
    return {"multiple": float(daily.iloc[-1] / capital), "max_dd": float((1 - daily / peak).max()),
            "btc_per_1k": float(qty_path[-1] / capital * 1000), "x_utilization": float((invested / daily).mean()),
            "x_longest_underwater_days": longest / 24, "x_round_trips": round_trips, "equity": daily}


# ----------------------------------------------------------------------------- L3 overlay
def crowding_flags(btc_daily: pd.DataFrame) -> pd.DataFrame:
    """Daily D1 (crowded shorts) and D2 (overheated longs) CONDITIONS (not onsets), indexed by the time
    they are known (end of day D = D+1 00:00)."""
    d = daily_inputs("BTCUSDT", btc_daily)
    p3 = expanding_percentile(d["funding3"], 180)
    p1 = expanding_percentile(d["funding1"], 180)
    oi_high = d["oi"] >= d["oi"].rolling(90, min_periods=90).max()
    out = pd.DataFrame({"d1": ((p3 < 10) & d["btc_up"]).astype(float), "d2": ((p1 > 95) & oi_high).astype(float)},
                       index=d.index + pd.Timedelta(days=1))
    return out


class S2Crowding(DCA200W):
    """L3: S2 (aggressive) with the weekly multiplier x0.5 while longs are overheated (D2) and x1.5
    while shorts are crowded in an uptrend (D1). Fear & Greed is not available, so D1 stands in for 'fear'."""
    key, name = "L3", "S2 × funding/OI crowding overlay"
    GRID = {"table": ["aggressive"]}

    def prepare(self):
        super().prepare()
        self.flags = crowding_flags(self.ctx.btc)

    def multiplier(self, d):
        m = super().multiplier(d)
        if not np.isfinite(m):
            return m
        if self.sig(self.flags["d2"], d) == 1:
            return m * 0.5
        if self.sig(self.flags["d1"], d) == 1:
            return m * 1.5
        return m
