"""Part B setups T1, T1b, T2, T3, T4, T5, T6.

Each setup has a small parameter grid (<= 12 combinations), an ordered list of optional
RULES used by the ablation ladder (SPEC_RULES = the rules as specified), and
`trades(market, asset, params, rules, costs)` returning closed trades with a `tf` column.
All signals use data up to the close of their signal bar; orders fill from the next bar.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from .engine import RISK, TRADE_COLS, Bars, Costs, Order, simulate
from .market import Market, pivots

DAY = pd.Timedelta(days=1)
BARS_PER_DAY = {"1m": 1440, "5m": 288, "15m": 96, "1h": 24, "4h": 6, "1d": 1}


class Setup:
    key = "?"
    name = "?"
    GRID: dict = {}
    RULES: list = []
    SPEC_RULES: list = []
    SIM_TF = None          # timeframe of the bars used to simulate exits (None = params["tf"])
    MIN_OOS_TRADES = 100

    @classmethod
    def grid(cls) -> list[dict]:
        keys = list(cls.GRID)
        g = [dict(zip(keys, c)) for c in itertools.product(*cls.GRID.values())]
        assert len(g) <= 12, f"{cls.key}: grid larger than 12"
        return g

    @classmethod
    def sim_tf(cls, p):
        return cls.SIM_TF or p["tf"]

    @classmethod
    def orders(cls, m: Market, asset: str, p: dict, rules: frozenset) -> list[Order]:
        raise NotImplementedError

    @classmethod
    def trades(cls, m: Market, asset: str, p: dict, rules, costs: Costs = Costs(), orders=None) -> pd.DataFrame:
        orders = cls.orders(m, asset, p, frozenset(rules)) if orders is None else orders
        t = simulate(m.bars(asset, cls.sim_tf(p)), orders, costs)
        t["tf"] = cls.sim_tf(p)
        return t

    @classmethod
    def eligible(cls, m: Market, asset: str, tf: str, rules) -> np.ndarray:
        """Bars where the setup's trend filter is true (random-entry baseline)."""
        d = m.df(asset, tf)
        if "trend" in rules:
            return (d["close"] > d["ema200"]).to_numpy(bool)
        return np.ones(len(d), bool)


# ----------------------------------------------------------------------------- T1 / T1b
class T1RangeReclaim(Setup):
    """Range over the last L bars (H, Lo); a sweep below Lo - 0.1 ATR reclaimed by a close above Lo
    within 3 bars -> buy next open. Stop = sweep low - 0.1 ATR; target H or 2R; time stop 2L bars."""
    key, name = "T1", "Range reclaim (liquidity sweep)"
    GRID = {"tf": ["1h", "4h", "1d"], "L": [30, 60], "target": ["H", "2R"]}
    RULES = ["touches", "width", "trend", "time_stop"]
    SPEC_RULES = ["touches", "width", "trend", "time_stop"]

    @classmethod
    def orders(cls, m, asset, p, rules):
        tf, L = p["tf"], p["L"]
        d = m.df(asset, tf)
        h, l, c = d["high"].to_numpy(), d["low"].to_numpy(), d["close"].to_numpy()
        atr = d["atr"].to_numpy()
        H = d["high"].shift(1).rolling(L, min_periods=L).max().to_numpy()
        Lo = d["low"].shift(1).rolling(L, min_periods=L).min().to_numpy()
        atr_prev = np.r_[np.nan, atr[:-1]]
        sweep = np.flatnonzero(l < Lo - 0.1 * atr_prev)
        up = d["btc_up"].to_numpy(bool)
        out, used_r = [], set()
        n = len(d)
        for s in sweep:
            rng = H[s] - Lo[s]
            if not (np.isfinite(rng) and rng > 0 and np.isfinite(atr_prev[s])):
                continue
            if "touches" in rules:
                hw, lw = h[s - L:s], l[s - L:s]
                if (hw >= H[s] - 0.15 * rng).sum() < 2 or (lw <= Lo[s] + 0.15 * rng).sum() < 2:
                    continue
            if "width" in rules and not (3 <= rng / atr_prev[s] <= 12):
                continue
            for r in range(s, min(s + 3, n)):
                if c[r] > Lo[s]:
                    break
            else:
                continue
            if r in used_r:
                continue
            if "trend" in rules and not up[r]:
                continue
            used_r.add(r)
            stop = l[s:r + 1].min() - 0.1 * atr[r]
            out.append(Order(sig_idx=r, valid_from=r + 1, valid_to=r + 1, stop=stop,
                             target=H[s] if p["target"] == "H" else np.nan,
                             target_r=2.0 if p["target"] == "2R" else np.nan,
                             cap=2 * L if "time_stop" in rules else None, atr=atr[r]))
        return out

    @classmethod
    def eligible(cls, m, asset, tf, rules):
        d = m.df(asset, tf)
        return d["btc_up"].to_numpy(bool) if "trend" in rules else np.ones(len(d), bool)


class T1bFractalReclaim(T1RangeReclaim):
    """T1 with Lo = the most recent confirmed fractal swing low (k=5) and H = the most recent
    confirmed fractal swing high; each swing low is used once. Time stop 120 bars."""
    key, name = "T1b", "Fractal-low reclaim"
    GRID = {"tf": ["1h", "4h", "1d"], "target": ["H", "2R"]}
    RULES = ["trend", "time_stop"]
    SPEC_RULES = ["trend", "time_stop"]
    K = 5

    @classmethod
    def orders(cls, m, asset, p, rules):
        d = m.df(asset, p["tf"])
        h, l, c, atr = (d[x].to_numpy() for x in ("high", "low", "close", "atr"))
        up = d["btc_up"].to_numpy(bool)
        ph, pl = pivots(h, cls.K, "high"), pivots(l, cls.K, "low")
        n, out = len(d), []
        lo_val = hi_val = np.nan
        lo_used = True
        s = 0
        while s < n:
            # pivots confirmed at the close of s-1 are known when bar s trades
            if s >= 1 and pl[s - 1]:
                lo_val, lo_used = l[s - 1 - cls.K], False
            if s >= 1 and ph[s - 1]:
                hi_val = h[s - 1 - cls.K]
            if (not lo_used and np.isfinite(atr[s - 1] if s else np.nan)
                    and l[s] < lo_val - 0.1 * atr[s - 1]):
                lo_used = True
                for r in range(s, min(s + 3, n)):
                    if c[r] > lo_val:
                        break
                else:
                    s += 1
                    continue
                if ("trend" not in rules) or up[r]:
                    stop = l[s:r + 1].min() - 0.1 * atr[r]
                    tgt = hi_val if p["target"] == "H" and np.isfinite(hi_val) and hi_val > lo_val else np.nan
                    if p["target"] == "2R" or np.isfinite(tgt):
                        out.append(Order(sig_idx=r, valid_from=r + 1, valid_to=r + 1, stop=stop, target=tgt,
                                         target_r=2.0 if p["target"] == "2R" else np.nan,
                                         cap=120 if "time_stop" in rules else None, atr=atr[r]))
            s += 1
        return out


# ----------------------------------------------------------------------------- T2
class T2VolumeBreakout(Setup):
    """5m green candle with volume and body >= m x their previous-10 averages; level = its high.
    On 1m: first candle closing above the level within 60 minutes -> buy next 1m open
    (or a retest limit at the level valid 30 minutes). Stop = signal low; target 1R/2R."""
    key, name = "T2", "Volume + body expansion breakout (5m/1m)"
    GRID = {"m": [1.5, 2.0], "entry": ["immediate", "retest"], "target_r": [1.0, 2.0]}
    RULES = ["body", "trend"]
    SPEC_RULES = ["body", "trend"]
    SIM_TF = "1m"
    START = pd.Timestamp("2021-01-01", tz="UTC")

    @classmethod
    def orders(cls, m, asset, p, rules):
        d5 = m.df(asset, "5m")
        b1 = m.bars(asset, "1m")
        v, body = d5["volume"], d5["body"]
        vm = v.shift(1).rolling(10, min_periods=10).mean()
        bm = body.shift(1).rolling(10, min_periods=10).mean()
        sig = d5["green"] & (v >= p["m"] * vm) & (d5.index >= cls.START)
        if "body" in rules:
            sig &= body >= p["m"] * bm
        if "trend" in rules:
            sig &= d5["close"] > d5["ema200"]
        idx = np.flatnonzero(sig.to_numpy(bool))
        t1 = b1.index.asi8
        closes = (d5.index[idx] + pd.Timedelta(minutes=5)).as_unit("ns").asi8
        starts = np.searchsorted(t1, closes)
        hi5, lo5, atr5 = d5["high"].to_numpy(), d5["low"].to_numpy(), d5["atr"].to_numpy()
        out = []
        for i, a in zip(idx, starts):
            if a >= len(b1):
                continue
            level = hi5[i]
            win = b1.c[a:a + 60]
            x = np.flatnonzero(win > level)
            if len(x) == 0:
                continue
            x = a + x[0]
            common = dict(sig_idx=x, stop=lo5[i], target_r=p["target_r"], atr=atr5[i])
            if p["entry"] == "immediate":
                out.append(Order(valid_from=x + 1, valid_to=x + 1, **common))
            else:
                out.append(Order(kind="limit", limit=level, valid_from=x + 1, valid_to=x + 30, **common))
        return out

    @classmethod
    def eligible(cls, m, asset, tf, rules):
        return Setup.eligible.__func__(cls, m, asset, "5m", rules)


# ----------------------------------------------------------------------------- T3
class T3TrendlineBreak(Setup):
    """In a pullback, a line through the last two confirmed descending fractal highs; a green
    close above it followed by another green candle -> buy next open. Stop = lowest low since
    the second pivot; target 2R."""
    key, name = "T3", "Trendline break + two green candles"
    GRID = {"tf": ["15m", "1h", "4h"], "k": [3, 5]}
    RULES = ["two_green", "trend"]
    SPEC_RULES = ["two_green", "trend"]

    @classmethod
    def orders(cls, m, asset, p, rules):
        d = m.df(asset, p["tf"])
        k = p["k"]
        o, h, l, c, atr, e200 = (d[x].to_numpy() for x in ("open", "high", "low", "close", "atr", "ema200"))
        green = c > o
        ph = pivots(h, k, "high")
        n, out = len(d), []
        piv: list[tuple[int, float]] = []
        used = None
        for t in range(1, n):
            if ph[t]:
                piv.append((t - k, h[t - k]))
            if len(piv) < 2:
                continue
            (i1, h1), (i2, h2) = piv[-2], piv[-1]
            if not h2 < h1 or (i1, i2) == used:
                continue
            slope = (h2 - h1) / (i2 - i1)
            y_t, y_p = h2 + slope * (t - i2), h2 + slope * (t - 1 - i2)
            if not (c[t] > y_t and c[t - 1] <= y_p and green[t]):
                continue
            sig = t
            if "two_green" in rules:
                if t + 1 >= n:
                    break  # the confirming candle has not closed yet
                if not green[t + 1]:
                    used = (i1, i2)
                    continue
                sig = t + 1
            used = (i1, i2)
            if "trend" in rules and not c[sig] > e200[sig]:
                continue
            stop = l[i2:sig + 1].min()
            out.append(Order(sig_idx=sig, valid_from=sig + 1, valid_to=sig + 1, stop=stop, target_r=2.0,
                             atr=atr[sig]))
        return out


# ----------------------------------------------------------------------------- T4
class T4StructureDemand(Setup):
    """Structure uptrend (a swing low is valid once price closes above the prior swing high; the
    trend is up while the latest valid low holds), demand zone = last candle before an impulse
    (body >= 2 ATR or 3-bar move >= 3 ATR) that follows a tight 5-bar consolidation (<= 1.5 ATR).
    Limit buy at the zone high, stop 0.1 ATR below the zone low, target = latest swing high,
    only if reward/risk >= 2.5. Pivots: fractal k=3."""
    key, name = "T4", "Market structure + demand zone + RR filter"
    GRID = {"tf": ["1h", "4h", "1d"]}
    RULES = ["consolidation", "structure", "rr"]
    SPEC_RULES = ["consolidation", "structure", "rr"]
    K = 3
    VALID_BARS = 100

    @classmethod
    def structure(cls, d: pd.DataFrame):
        """Per bar (known at its close): trend_up flag and the latest confirmed swing high."""
        h, l, c = d["high"].to_numpy(), d["low"].to_numpy(), d["close"].to_numpy()
        ph, pl = pivots(h, cls.K, "high"), pivots(l, cls.K, "low")
        n = len(d)
        up = np.zeros(n, bool)
        last_high = np.full(n, np.nan)
        cur_high, pending, valid_low = np.nan, [], None
        for t in range(n):
            if ph[t]:
                cur_high = h[t - cls.K]
            if pl[t]:
                pending.append((l[t - cls.K], cur_high))  # (low, swing high before it)
            for lowv, prior_high in list(pending):
                if np.isfinite(prior_high) and c[t] > prior_high:
                    valid_low = lowv
                    pending.remove((lowv, prior_high))
            if valid_low is not None and c[t] < valid_low:
                valid_low = None
            up[t] = valid_low is not None
            last_high[t] = cur_high
        return up, last_high

    @classmethod
    def orders(cls, m, asset, p, rules):
        d = m.df(asset, p["tf"])
        o, h, l, c, atr, body = (d[x].to_numpy() for x in ("open", "high", "low", "close", "atr", "body"))
        up, last_high = cls.structure(d)
        n, out = len(d), []
        for i in range(6, n):
            a = atr[i - 1]
            if not np.isfinite(a) or a <= 0:
                continue
            if body[i] >= 2 * a and c[i] > o[i]:
                known = i
            elif i + 2 < n and c[i + 2] - o[i] >= 3 * a:
                known = i + 2
            else:
                continue
            z = i - 1
            if "consolidation" in rules and h[z - 4:z + 1].max() - l[z - 4:z + 1].min() > 1.5 * atr[z]:
                continue
            if "structure" in rules and not up[known]:
                continue
            entry, stop, tgt = h[z], l[z] - 0.1 * atr[z], last_high[known]
            if not (np.isfinite(tgt) and tgt > entry > stop):
                continue
            if "rr" in rules and (tgt - entry) / (entry - stop) < 2.5:
                continue
            out.append(Order(sig_idx=known, kind="limit", limit=entry, valid_from=known + 1,
                             valid_to=known + cls.VALID_BARS, stop=stop, target=tgt, cancel_below=l[z],
                             atr=atr[z]))
        return out

    @classmethod
    def eligible(cls, m, asset, tf, rules):
        d = m.df(asset, tf)
        return cls.structure(d)[0] if "structure" in rules else np.ones(len(d), bool)


# ----------------------------------------------------------------------------- T5
class T5EmaRsiEngulfing(Setup):
    """Close > EMA200, RSI14 > 50, bullish engulfing candle closed -> buy next open.
    Stop = entry - 2 x engulfing candle range; target 2R."""
    key, name = "T5", "EMA200 + RSI + bullish engulfing"
    GRID = {"tf": ["15m", "1h", "4h"]}
    RULES = ["trend", "rsi"]
    SPEC_RULES = ["trend", "rsi"]

    @classmethod
    def orders(cls, m, asset, p, rules):
        d = m.df(asset, p["tf"])
        o, h, l, c = (d[x].to_numpy() for x in ("open", "high", "low", "close"))
        po, pc = np.r_[np.nan, o[:-1]], np.r_[np.nan, c[:-1]]
        eng = (pc < po) & (c > o) & (o <= pc) & (c >= po) & ((c - o) > (po - pc))
        if "trend" in rules:
            eng &= c > d["ema200"].to_numpy()
        if "rsi" in rules:
            eng &= d["rsi"].to_numpy() > 50
        atr = d["atr"].to_numpy()
        return [Order(sig_idx=i, valid_from=i + 1, valid_to=i + 1, stop_offset=2 * (h[i] - l[i]), target_r=2.0,
                      atr=atr[i]) for i in np.flatnonzero(eng)]


# ----------------------------------------------------------------------------- T6
class T6BaseCrack(Setup):
    """QFL: base = confirmed fractal swing low (k=3) followed by a bounce >= b% within 20 bars.
    Crack = close below base by d% -> 4 equal limit tranches at base x (1-d), (1-2d), (1-3d), (1-4d).
    Exit all at the base (limit); failure exit at the next open after a close below base x (1-5d),
    or after 30 days. Sized so the loss at the failure level (all 4 filled) = 1.5% of equity."""
    key, name = "T6", "Base-crack tranche buying (QFL)"
    GRID = {"tf": ["1h", "4h"], "b": [0.03, 0.05], "d": [0.02, 0.04]}
    RULES = ["time30", "trend"]
    SPEC_RULES = ["time30"]          # spec: no trend filter (also reported with it via the ablation)
    K = 3

    @classmethod
    def events(cls, m, asset, p, rules):
        d = m.df(asset, p["tf"])
        h, l, c, e200, atr = (d[x].to_numpy() for x in ("high", "low", "close", "ema200", "atr"))
        pl = pivots(l, cls.K, "low")
        n, ev = len(d), []
        cand: list[tuple[int, float]] = []     # pivot lows waiting for their bounce
        base = None                             # (price, active_from)
        for t in range(n):
            if pl[t]:
                cand.append((t - cls.K, l[t - cls.K]))
            for i, pv in list(cand):
                if t - i > 20:
                    cand.remove((i, pv))
                elif h[t] >= pv * (1 + p["b"]) and t > i:
                    base = (pv, t)               # bounce confirmed at t
                    cand.remove((i, pv))
            if base is not None and t > base[1] and c[t] < base[0] * (1 - p["d"]):
                if "trend" not in rules or c[t] > e200[t]:
                    ev.append((t, base[0], atr[t]))
                base = None                      # each base is used once
        return ev

    @classmethod
    def trades(cls, m, asset, p, rules, costs: Costs = Costs(), orders=None):
        b = m.bars(asset, p["tf"])
        ev = cls.events(m, asset, p, frozenset(rules)) if orders is None else orders
        dd, fee, slip = p["d"], costs.fee, costs.slip
        cap = 30 * BARS_PER_DAY[p["tf"]] if "time30" in rules else None
        rows, free_from = [], 0
        for t, P, a in ev:
            j0 = t + 1
            if j0 <= free_from or j0 >= len(b):
                continue
            levels = [P * (1 - k * dd) for k in range(1, 5)]
            fail = P * (1 - 5 * dd)
            unit_risk = sum(L * (1 + slip) * (1 + fee) - fail * (1 - slip) * (1 - fee) for L in levels)
            notional = sum(L * (1 + slip) * (1 + fee) for L in levels)
            q = min(RISK / unit_risk, 1.0 / notional)   # per-tranche units for $1 of equity
            filled, cost, first = [], 0.0, None
            exit_bar = exit_px = None
            why = "end"
            for j in range(j0, len(b)):
                new = [L for L in levels if L not in filled and b.l[j] <= L]
                for L in new:
                    px = min(b.o[j], L)
                    filled.append(L)
                    cost += q * px * (1 + slip) * (1 + fee)
                    first = j if first is None else first
                if first is None:
                    continue
                if j > first and b.h[j] >= P:
                    exit_bar, exit_px, why = j, max(b.o[j], P), "target"
                    break
                if b.c[j] < fail:
                    jj = min(j + 1, len(b) - 1)
                    exit_bar, exit_px, why = jj, b.o[jj], "stop"
                    break
                if cap is not None and j - first >= cap:
                    exit_bar, exit_px, why = j, b.c[j], "time"
                    break
            if first is None:
                continue
            if exit_bar is None:
                exit_bar, exit_px = len(b) - 1, b.c[-1]
            units = q * len(filled)
            pnl = units * exit_px * (1 - slip) * (1 - fee) - cost
            avg = cost / units / ((1 + slip) * (1 + fee))
            free_from = exit_bar
            rows.append((b.index[t], b.index[first], b.index[exit_bar], avg, exit_px, fail, P,
                         pnl / (q * unit_risk), pnl, exit_bar - first + 1, why, a,
                         (avg - fail) / a if a > 0 else np.nan, (P - avg) / a if a > 0 else np.nan, cap, first))
        t = pd.DataFrame(rows, columns=TRADE_COLS)
        t["tf"] = p["tf"]
        return t


SETUPS = [T1RangeReclaim, T1bFractalReclaim, T2VolumeBreakout, T3TrendlineBreak, T4StructureDemand,
          T5EmaRsiEngulfing, T6BaseCrack]
