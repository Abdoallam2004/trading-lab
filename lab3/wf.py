"""Part B validation: rolling walk-forward (train 12 months / test 3 months), metrics,
random-entry baseline, Deflated Sharpe Ratio and the ablation ladder."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import NormalDist

import numpy as np
import pandas as pd

from .data import DEV_END
from .engine import Costs, scan_exit
from .market import Market
from .setups import BARS_PER_DAY, T6BaseCrack

TRAIN_MONTHS = 12
MIN_TRAIN_TRADES = 30
DEV_START = pd.Timestamp("2020-01-01", tz="UTC")
DEV_TESTS = list(pd.date_range("2021-01-01", "2025-07-01", freq="QS", tz="UTC"))
HOLDOUT_TESTS = list(pd.date_range("2025-10-01", "2026-07-01", freq="QS", tz="UTC"))
ND = NormalDist()


def test_end(ts: pd.Timestamp) -> pd.Timestamp:
    return ts + pd.DateOffset(months=3)


def key_of(p: dict) -> tuple:
    return tuple(sorted(p.items()))


@dataclass
class WFResult:
    setup: str
    rules: tuple
    asset: str
    costs: Costs
    trades: pd.DataFrame
    choices: list                 # chosen params per window (None = no set had >= 30 train trades)
    train_exp: list
    windows: list
    span: tuple = None
    meta: dict = field(default_factory=dict)

    @property
    def expectancy(self) -> float:
        return float(self.trades["r"].mean()) if len(self.trades) else -np.inf


class Lab:
    def __init__(self, market: Market, log=print):
        self.m = market
        self.log = log
        self._orders: dict = {}
        self._trades: dict = {}
        self.registry: dict = {}      # every (setup, rules, params) evaluated on BTC dev data -> per-trade SR

    # -------------------------------------------------------------- trades
    def trades(self, S, asset, p, rules, costs: Costs = Costs()) -> pd.DataFrame:
        rules = frozenset(rules)
        ok = (S.key, asset, key_of(p), rules)
        if ok not in self._orders:
            self._orders[ok] = (S.events(self.m, asset, p, rules) if S is T6BaseCrack
                                else S.orders(self.m, asset, p, rules))
        tk = ok + (costs,)
        if tk not in self._trades:
            t = S.trades(self.m, asset, p, rules, costs, orders=self._orders[ok])
            self._trades[tk] = t
            if asset == "BTCUSDT" and costs == Costs() and not self.m.holdout:
                dev = t[(t["entry_time"] >= DEV_START) & (t["entry_time"] <= DEV_END)]["r"]
                sd = dev.std()
                self.registry[(S.key, tuple(sorted(rules)), key_of(p))] = {
                    "n": len(dev), "sr": float(dev.mean() / sd) if len(dev) > 2 and sd > 0 else np.nan}
        return self._trades[tk]

    # -------------------------------------------------------------- walk-forward
    def walk_forward(self, S, rules, asset="BTCUSDT", costs: Costs = Costs(), choices=None,
                     tests=DEV_TESTS) -> WFResult:
        rules = tuple(sorted(rules))
        grid = S.grid()
        picked, train_exp, parts = [], [], []
        for w, ts in enumerate(tests):
            tr0, te = ts - pd.DateOffset(months=TRAIN_MONTHS), test_end(ts)
            if choices is None:
                best, best_e = None, -np.inf
                for p in grid:
                    t = self.trades(S, "BTCUSDT", p, rules)
                    tr = t[(t["entry_time"] >= tr0) & (t["entry_time"] < ts)]
                    if len(tr) >= MIN_TRAIN_TRADES and tr["r"].mean() > best_e:
                        best, best_e = p, float(tr["r"].mean())
                picked.append(best)
                train_exp.append(best_e if best is not None else np.nan)
            else:
                best = choices[w]
                picked.append(best)
                train_exp.append(np.nan)
            if best is None:
                continue
            t = self.trades(S, asset, best, rules, costs)
            seg = t[(t["entry_time"] >= ts) & (t["entry_time"] < te)].copy()
            seg["window"] = w
            seg["params"] = str(best)
            parts.append(seg)
        trades = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["r", "ret", "entry_time"])
        first = next((tests[w] for w, c in enumerate(picked) if c is not None), tests[0])
        last = test_end(tests[-1]) - pd.Timedelta(seconds=1)
        return WFResult(S.key, rules, asset, costs, trades, picked, train_exp, tests, (first, last))


# ----------------------------------------------------------------------------- metrics
def metrics(t: pd.DataFrame, span: tuple) -> dict:
    n = len(t)
    a, b = span
    years = max((b - a).days / 365.25, 1e-9)
    if n == 0:
        return {"trades": 0, "win_rate": np.nan, "avg_win_r": np.nan, "avg_loss_r": np.nan, "expectancy": np.nan,
                "profit_factor": np.nan, "cagr": 0.0, "max_dd": 0.0, "exposure": 0.0, "pct_months_up": np.nan,
                "streak_trades": 0, "streak_days": 0, "sharpe_trade": np.nan}
    t = t.sort_values("exit_time")
    r = t["r"].to_numpy()
    eq = np.cumprod(1 + t["ret"].to_numpy())
    peak = np.maximum.accumulate(np.r_[1.0, eq])[1:]
    gains, losses = r[r > 0].sum(), -r[r < 0].sum()
    dur = sum((pd.Timestamp(x) - pd.Timestamp(e)).total_seconds() for e, x in zip(t["entry_time"], t["exit_time"]))
    monthly = t.groupby(t["exit_time"].dt.tz_localize(None).dt.to_period("M"))["ret"].apply(lambda s: np.prod(1 + s) - 1)
    # longest losing streak (by trades, and the calendar days it spanned)
    best_n = best_days = cur_n = 0
    cur_start = None
    for e, x, rr in zip(t["entry_time"], t["exit_time"], r):
        if rr < 0:
            cur_n += 1
            cur_start = e if cur_n == 1 else cur_start
            if cur_n > best_n:
                best_n, best_days = cur_n, (x - cur_start).days
        else:
            cur_n = 0
    return {"trades": n, "win_rate": float((r > 0).mean()),
            "avg_win_r": float(r[r > 0].mean()) if (r > 0).any() else np.nan,
            "avg_loss_r": float(r[r <= 0].mean()) if (r <= 0).any() else np.nan,
            "expectancy": float(r.mean()), "profit_factor": float(gains / losses) if losses > 0 else np.inf,
            "cagr": float(eq[-1] ** (1 / years) - 1), "max_dd": float((1 - eq / peak).max()),
            "exposure": float(dur / (b - a).total_seconds()), "pct_months_up": float((monthly > 0).mean()),
            "streak_trades": best_n, "streak_days": best_days,
            "sharpe_trade": float(r.mean() / r.std(ddof=1)) if n > 2 and r.std(ddof=1) > 0 else np.nan}


def btc_buy_hold(m: Market, span: tuple) -> dict:
    d = m.df("BTCUSDT", "1d")["close"]
    a = d[d.index >= span[0].normalize()].iloc[0]
    b = d[d.index <= span[1]].iloc[-1]
    years = (span[1] - span[0]).days / 365.25
    return {"return": float(b / a - 1), "cagr": float((b / a) ** (1 / years) - 1)}


# ----------------------------------------------------------------------------- random baseline
def random_baseline(lab: Lab, S, wf: WFResult, n_sims: int = 1000, seed: int = 7, costs: Costs = Costs()):
    """1,000 random-entry runs with the same number of trades, same stop / target distances in ATR
    (taken trade by trade) and the same holding cap, entering at random bars of the same timeframe and
    test window where the setup's trend filter is true. Returns (sim expectancies, R matrix)."""
    t = wf.trades.reset_index(drop=True)
    if len(t) == 0:
        return np.array([]), np.zeros((0, 0))
    rng = np.random.default_rng(seed)
    R = np.full((n_sims, len(t)), np.nan)
    fee, slip = costs.fee, costs.slip
    for (tf, w), g in t.groupby(["tf", "window"]):
        sim_tf = "5m" if tf == "1m" else tf   # T2: random entries on its 5m signal timeframe
        b = lab.m.bars(wf.asset, sim_tf)
        atr = lab.m.df(wf.asset, sim_tf)["atr"].to_numpy()
        elig = S.eligible(lab.m, wf.asset, sim_tf, wf.rules)
        ts, te = wf.windows[w], test_end(wf.windows[w])
        lo, hi = np.searchsorted(b.index, ts), np.searchsorted(b.index, te) - 2
        pool = np.flatnonzero(elig[lo:hi] & np.isfinite(atr[lo:hi]) & (atr[lo:hi] > 0)) + lo
        if len(pool) == 0:
            continue
        caps = g["cap"].to_numpy(float)
        maxbars = int(np.nanmax(g["bars"])) if len(g) else 100
        scale = 5 if tf == "1m" else 1
        for col, tr in zip(g.index, g.itertuples()):
            cap = int(tr.cap) if pd.notna(tr.cap) else int(math.ceil(maxbars / scale))
            ks = rng.choice(pool, size=n_sims)
            for s_i, k in enumerate(ks):
                fill = b.o[k + 1]
                stop = fill - tr.stop_atr * atr[k]
                tgt = fill + tr.target_atr * atr[k] if np.isfinite(tr.target_atr) else np.nan
                if not stop < fill:
                    continue
                kx, px, _ = scan_exit(b, k + 1, stop, tgt, cap, False)
                e_cost = fill * (1 + slip) * (1 + fee)
                R[s_i, col] = (px * (1 - slip) * (1 - fee) - e_cost) / (e_cost - stop * (1 - slip) * (1 - fee))
    return np.nanmean(R, axis=1), R


# ----------------------------------------------------------------------------- deflated Sharpe
def deflated_sharpe(r: np.ndarray, n_trials: int, sr_var: float) -> float:
    """Bailey & López de Prado (2014), on per-trade returns in R."""
    r = np.asarray(r, float)
    T = len(r)
    if T < 3 or r.std(ddof=1) == 0 or n_trials < 2 or not np.isfinite(sr_var):
        return np.nan
    sr = r.mean() / r.std(ddof=1)
    z = (r - r.mean()) / r.std(ddof=0)
    skew, kurt = float((z ** 3).mean()), float((z ** 4).mean())
    g = 0.5772156649
    sr0 = math.sqrt(sr_var) * ((1 - g) * ND.inv_cdf(1 - 1 / n_trials) + g * ND.inv_cdf(1 - 1 / (n_trials * math.e)))
    denom = 1 - skew * sr + (kurt - 1) / 4 * sr ** 2
    if denom <= 0:
        return np.nan
    return float(ND.cdf((sr - sr0) * math.sqrt(T - 1) / math.sqrt(denom)))


# ----------------------------------------------------------------------------- ablation
def ablation(lab: Lab, S) -> dict:
    """Start from the bare trigger and add one rule at a time; keep a rule only if it improves
    the stitched OOS expectancy. Also runs the rules exactly as specified."""
    steps = []
    base = lab.walk_forward(S, [])
    steps.append({"step": "bare trigger", "rules": (), "expectancy": base.expectancy, "trades": len(base.trades),
                  "kept": True})
    kept, cur = [], base.expectancy
    results = {(): base}
    for rule in S.RULES:
        cand = kept + [rule]
        wf = lab.walk_forward(S, cand)
        results[tuple(sorted(cand))] = wf
        keep = wf.expectancy > cur
        steps.append({"step": f"+ {rule}", "rules": tuple(cand), "expectancy": wf.expectancy,
                      "trades": len(wf.trades), "kept": keep})
        if keep:
            kept, cur = cand, wf.expectancy
    spec = tuple(sorted(S.SPEC_RULES))
    if spec not in results:
        results[spec] = lab.walk_forward(S, list(spec))
    return {"steps": steps, "final_rules": tuple(sorted(kept)), "results": results, "spec_rules": spec}
