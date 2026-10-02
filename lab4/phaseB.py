"""Phase B: Lab 3's setups re-run with the user's real execution (limit ladders, BNB fees).

Each Lab 3 order becomes a Signal: anchor = the signal bar's close (market-entry setups) or the
original limit (T4); reference low = the structural low Lab 3 hung its stop under; entry limits stay
live for 3 bars (T4: Lab 3's 100 bars, cancelled when the zone breaks). T6 keeps its own 4-tranche
ladder and base exit, so only cost scenarios and fill models change for it.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from lab3.engine import TRADE_COLS
from lab3.market import Market
from lab3.setups import BARS_PER_DAY, T1bFractalReclaim, T1RangeReclaim, T3TrendlineBreak, T4StructureDemand, \
    T5EmaRsiEngulfing, T6BaseCrack
from lab3.wf import DEV_TESTS, MIN_TRAIN_TRADES, TRAIN_MONTHS, WFResult, key_of, test_end

from lab.config import REPORTS_DIR

from .execution import C0, RISK, THROUGH, Exec, Scenario, Signal, simulate

SETUPS_B = [T1RangeReclaim, T1bFractalReclaim, T3TrendlineBreak, T4StructureDemand, T5EmaRsiEngulfing, T6BaseCrack]
ENTRY_WINDOW = 3


def frozen_rules() -> dict:
    fz = json.loads((REPORTS_DIR / "lab3_frozen.json").read_text())
    return {k: tuple(v["rules"]) for k, v in fz["setups"].items()}


def to_signals(S, m: Market, asset: str, p: dict, rules) -> list[Signal]:
    d = m.df(asset, S.sim_tf(p))
    c, l = d["close"].to_numpy(), d["low"].to_numpy()
    out = []
    for o in S.orders(m, asset, p, frozenset(rules)):
        if S is T5EmaRsiEngulfing:
            ref = l[o.sig_idx]
        elif S is T3TrendlineBreak:
            ref = o.stop
        else:   # T1, T1b, T4 hung the stop 0.1 ATR under the reference low
            ref = o.stop + 0.1 * o.atr
        if o.kind == "limit":
            sg = Signal(o.sig_idx, o.valid_from, o.valid_to, o.limit, ref, o.atr, o.target, o.target_r, o.cap,
                        o.cancel_below)
        else:
            sg = Signal(o.sig_idx, o.valid_from, o.valid_from + ENTRY_WINDOW - 1, c[o.sig_idx], ref, o.atr,
                        o.target, o.target_r, o.cap)
        if np.isfinite(sg.atr) and sg.atr > 0 and np.isfinite(ref):
            out.append(sg)
    return out


def t6_trades(m: Market, asset: str, p: dict, rules, sc: Scenario, fill: str = "through") -> pd.DataFrame:
    """Lab 3's T6 with Lab 4 costs and fill models (tranche and base limits need trade-through)."""
    b = m.bars(asset, p["tf"])
    ev = T6BaseCrack.events(m, asset, p, frozenset(rules))
    tt = THROUGH if fill == "through" else 0.0
    dd, fee, ls, ss = p["d"], sc.fee, sc.limit_slip, sc.stop_slip
    cap = 30 * BARS_PER_DAY[p["tf"]] if "time30" in rules else None
    rows, free_from = [], 0
    for t, P, a in ev:
        j0 = t + 1
        if j0 <= free_from or j0 >= len(b):
            continue
        levels = [P * (1 - k * dd) for k in range(1, 5)]
        fail = P * (1 - 5 * dd)
        unit_risk = sum(L * (1 + fee) - fail * (1 - ss) * (1 - fee) for L in levels)
        q = min(RISK / unit_risk, 1.0 / sum(L * (1 + fee) for L in levels))
        filled, cost, first, exit_bar, exit_px, why = [], 0.0, None, None, None, "end"
        for j in range(j0, len(b)):
            for L in levels:
                if L not in filled and b.l[j] <= L * (1 - tt):
                    filled.append(L)
                    cost += q * min(b.o[j], L) * (1 + ls) * (1 + fee)
                    first = j if first is None else first
            if first is None:
                continue
            if j > first and b.h[j] >= P * (1 + tt):
                exit_bar, exit_px, why = j, max(b.o[j], P) * (1 - ls), "target"
                break
            if b.c[j] < fail:
                jj = min(j + 1, len(b) - 1)
                exit_bar, exit_px, why = jj, b.o[jj] * (1 - ss), "stop"
                break
            if cap is not None and j - first >= cap:
                exit_bar, exit_px, why = j, b.c[j] * (1 - ls), "time"
                break
        if first is None:
            continue
        if exit_bar is None:
            exit_bar, exit_px = len(b) - 1, b.c[-1]
        units = q * len(filled)
        pnl = units * exit_px * (1 - fee) - cost
        avg = cost / units / (1 + fee)
        free_from = exit_bar
        rows.append((b.index[t], b.index[first], b.index[exit_bar], avg, exit_px, fail, pnl / (q * unit_risk), pnl,
                     exit_bar - first + 1, why, len(filled), a, (avg - fail) / a if a > 0 else np.nan,
                     (P - avg) / a if a > 0 else np.nan, cap, first))
    return pd.DataFrame(rows, columns=["sig_time", "entry_time", "exit_time", "entry", "exit", "stop", "r", "ret",
                                       "bars", "reason", "fills", "atr", "stop_atr", "target_atr", "cap", "entry_idx"])


class LabB:
    """Trade cache + walk-forward for (setup, execution, scenario, fill) configurations."""

    def __init__(self, m: Market):
        self.m = m
        self._sig: dict = {}
        self._tr: dict = {}
        self.registry: dict = {}   # every configuration evaluated -> per-trade Sharpe on BTC dev data

    def trades(self, S, asset, p, rules, ex: Exec, sc: Scenario, fill="through") -> pd.DataFrame:
        k = (S.key, asset, key_of(p), tuple(rules), ex, sc, fill)
        if k not in self._tr:
            if S is T6BaseCrack:
                t = t6_trades(self.m, asset, p, rules, sc, fill)
            else:
                sk = (S.key, asset, key_of(p), tuple(rules))
                if sk not in self._sig:
                    self._sig[sk] = to_signals(S, self.m, asset, p, rules)
                t = simulate(self.m.bars(asset, S.sim_tf(p)), self._sig[sk], ex, sc, fill)
            t["tf"] = S.sim_tf(p)
            self._tr[k] = t
            if asset == "BTCUSDT":
                r = t["r"]
                sd = r.std()
                self.registry[(S.key, ex.label, sc.name, fill, key_of(p))] = {
                    "n": len(r), "sr": float(r.mean() / sd) if len(r) > 2 and sd > 0 else np.nan}
        return self._tr[k]

    def walk_forward(self, S, rules, ex: Exec, sc: Scenario, fill="through", asset="BTCUSDT", choices=None,
                     tests=DEV_TESTS) -> WFResult:
        picked, train_exp, parts = [], [], []
        for w, ts in enumerate(tests):
            tr0, te = ts - pd.DateOffset(months=TRAIN_MONTHS), test_end(ts)
            if choices is None:
                best, best_e = None, -np.inf
                for p in S.grid():
                    t = self.trades(S, "BTCUSDT", p, rules, ex, sc, fill)
                    tr = t[(t["entry_time"] >= tr0) & (t["entry_time"] < ts)]
                    if len(tr) >= MIN_TRAIN_TRADES and tr["r"].mean() > best_e:
                        best, best_e = p, float(tr["r"].mean())
            else:
                best, best_e = choices[w], np.nan
            picked.append(best)
            train_exp.append(best_e if best is not None else np.nan)
            if best is None:
                continue
            t = self.trades(S, asset, best, rules, ex, sc, fill)
            seg = t[(t["entry_time"] >= ts) & (t["entry_time"] < te)].copy()
            seg["window"], seg["params"] = w, str(best)
            parts.append(seg)
        trades = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=TRADE_COLS + ["tf"])
        first = next((tests[w] for w, c in enumerate(picked) if c is not None), tests[0])
        return WFResult(S.key, tuple(rules), asset, sc, trades, picked, train_exp, tests,
                        (first, test_end(tests[-1]) - pd.Timedelta(seconds=1)), {"exec": ex, "fill": fill})


def random_baseline(lab: "LabB", S, rules, wf: WFResult, ex: Exec, sc: Scenario, n_sims: int = 1000,
                    seed: int = 11, fill: str = "through") -> np.ndarray:
    """Random entries (same timeframe, test quarter and trend filter as each OOS trade) with the same
    execution model, stop distance and target distance in ATR and holding cap. Returns the
    expectancy of each of the n_sims runs."""
    from .execution import THROUGH as TT, Signal as Sig, run_trade, trade_r
    t = wf.trades.reset_index(drop=True)
    if len(t) == 0:
        return np.array([])
    rng = np.random.default_rng(seed)
    R = np.full((n_sims, len(t)), np.nan)
    tt = TT if fill == "through" else 0.0
    for (tf, w), g in t.groupby(["tf", "window"]):
        b = lab.m.bars(wf.asset, tf)
        d = lab.m.df(wf.asset, tf)
        atr, close = d["atr"].to_numpy(), d["close"].to_numpy()
        elig = S.eligible(lab.m, wf.asset, tf, rules)
        lo, hi = np.searchsorted(b.index, wf.windows[w]), np.searchsorted(b.index, test_end(wf.windows[w])) - 4
        pool = np.flatnonzero(elig[lo:hi] & np.isfinite(atr[lo:hi]) & (atr[lo:hi] > 0)) + lo
        if len(pool) == 0:
            continue
        maxbars = int(np.nanmax(g["bars"]))
        for col, tr in zip(g.index, g.itertuples()):
            cap = int(tr.cap) if pd.notna(tr.cap) else maxbars
            for s_i, k in enumerate(rng.choice(pool, size=n_sims)):
                a = atr[k]
                stop = close[k] - tr.stop_atr * a
                ref = stop / (1 - 0.001) if ex.stop == "S-a" else stop + 0.5 * a
                sg = Sig(k, k + 1, k + ENTRY_WINDOW, close[k], ref, a,
                         target=close[k] + tr.target_atr * a if ex.exit == "X1" else np.nan, cap=cap)
                res = run_trade(b, sg, ex, sc, tt, len(b))
                if res is not None:
                    R[s_i, col] = trade_r(res)
    return np.nanmean(R, axis=1)


def t6_signals_for_random(*_):
    raise NotImplementedError
