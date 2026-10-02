"""Part A: fair re-test of Lab 2's long-horizon rules with rolling starts, plus a graded market gate.

Every rule runs from the first Monday of every month 2018-01 .. 2022-09 for 3 years
(no run uses data after 2025-09-30), in frame A (lump sum $10,000 vs B1 buy & hold)
and frame B ($100 every Monday vs B2 plain DCA). Lab 2's parameter grids are frozen:
every grid member is reported, nothing is selected.
"""
from __future__ import annotations

import bisect
import itertools

import numpy as np
import pandas as pd

from lab2 import data as d2
from lab2 import signals as sg
from lab2.sim import Prices, metrics, run
from lab2.strategies import (BTC, BuyHold, Context, DCA200W, DrawdownDCA, LogRegBand, MVRVZ, PlainDCA,
                             RegimeFilter, Strategy)

from .data import DEV_END

HORIZON_YEARS = 3
FIRST_START, LAST_START = "2018-01", "2022-09"
WIN_FRAC, = (0.60,)


# ----------------------------------------------------------------------------- data
def build_context() -> tuple[Context, Prices]:
    btc = d2.load_full(BTC)
    btc = btc[btc.index <= DEV_END]
    cm = d2.load_coinmetrics()
    cm = cm[cm.index <= DEV_END]
    ctx = Context(d2.signal_price(btc, cm), d2.mvrv_inputs(cm, btc), btc=btc)
    return ctx, Prices({BTC: btc})


def rolling_starts() -> list[pd.Timestamp]:
    out = []
    for m in pd.period_range(FIRST_START, LAST_START, freq="M"):
        d = m.to_timestamp()
        d = d + pd.Timedelta(days=(7 - d.dayofweek) % 7)  # first Monday of the month
        out.append(d.tz_localize("UTC"))
    return out


def horizon_end(start: pd.Timestamp) -> pd.Timestamp:
    return start + pd.DateOffset(years=HORIZON_YEARS) - pd.Timedelta(days=1)


# ----------------------------------------------------------------------------- market gate
def expanding_percentile(x: pd.Series, min_obs: int = 365) -> pd.Series:
    """Percentile (0-100) of x_t among all observations up to and including t."""
    seen: list[float] = []
    out = np.full(len(x), np.nan)
    for i, v in enumerate(x.to_numpy(float)):
        if not np.isfinite(v):
            continue
        bisect.insort(seen, v)
        if len(seen) >= min_obs:
            out[i] = 100.0 * bisect.bisect_right(seen, v) / len(seen)
    return pd.Series(out, index=x.index)


def gate_components(sig_price: pd.Series, mvrv: pd.DataFrame) -> pd.DataFrame:
    """Four point-in-time sub-scores, 0-100 each (high = favourable for holding BTC)."""
    sma200 = sig_price.rolling(200, min_periods=200).mean()
    vol30 = np.log(sig_price).diff().rolling(30, min_periods=30).std()
    mz = sg.mvrv_z(mvrv).reindex(sig_price.index)
    comp = pd.DataFrame({
        "trend": expanding_percentile(sig_price / sma200),
        "value": 100 - expanding_percentile(mz),
        "drawdown": expanding_percentile(sg.drawdown_from_ath(sig_price)),
        "calm": 100 - expanding_percentile(vol30),
    })
    comp["score"] = comp[["trend", "value", "drawdown", "calm"]].mean(axis=1, skipna=False)
    return comp


EXPOSURE_MAPS = {
    "70/40": [(70, 1.0), (40, 0.6), (-np.inf, 0.0)],
    "60/30": [(60, 1.0), (30, 0.6), (-np.inf, 0.0)],
}


def exposure(score: float, mapping: str) -> float:
    if not np.isfinite(score):
        return np.nan
    return next(e for lo, e in EXPOSURE_MAPS[mapping] if score >= lo)


class _Gate(Strategy):
    GRID = {"map": list(EXPOSURE_MAPS)}
    _cache: dict = {}

    def prepare(self):
        key = id(self.ctx)
        if key not in _Gate._cache:
            _Gate._cache[key] = gate_components(self.ctx.sig_price, self.ctx.mvrv)["score"]
        self.score = _Gate._cache[key]

    def target(self, d) -> float:
        return exposure(self.sig(self.score, d), self.params["map"])


class GateLump(_Gate):
    """A2(i): lump sum held at the gate's exposure (0 / 60 / 100% BTC), rebalanced on Mondays,
    skipping drifts smaller than 5% of equity."""
    key, name = "A2-lump", "Market gate, lump sum"

    def step(self, d, acct, prices):
        if d.dayofweek != 0:
            return
        e = self.target(d)
        if not np.isfinite(e):
            e = 1.0  # gate not warmed up yet -> plain holding
        px = prices.open.at[d, BTC]
        eq = acct.value({BTC: px} if BTC in acct.qty else {})
        cur = acct.qty.get(BTC, 0.0) * px / eq if eq > 0 else 0.0
        if abs(cur - e) >= 0.05 or (e == 0 and cur > 0):
            acct.rebalance({BTC: e} if e > 0 else {}, {BTC: px}, min_frac=0.0)


class GateDCA(_Gate):
    """A2(ii): weekly budget = $100 + 1/4 of the saved reserve; buy = exposure x budget;
    whatever is not spent stays in the 0% reserve. Never sells."""
    key, name = "A2-dca", "Market gate, weekly DCA"

    def step(self, d, acct, prices):
        if d.dayofweek != 0:
            return
        e = self.target(d)
        if not np.isfinite(e):
            e = 1.0
        reserve = max(acct.cash - self.base, 0.0)
        acct.buy(BTC, e * (self.base + reserve / 4), prices.open.at[d, BTC])


LAB2_RULES = [RegimeFilter, DCA200W, DrawdownDCA, LogRegBand, MVRVZ]


def grid(cls) -> list[dict]:
    keys = list(cls.GRID)
    return [dict(zip(keys, c)) for c in itertools.product(*cls.GRID.values())]


def rules_for(frame: str) -> list[tuple]:
    out = [(cls, p) for cls in LAB2_RULES for p in grid(cls)]
    gate = GateLump if frame == "A" else GateDCA
    out += [(gate, p) for p in grid(gate)]
    return out


def bench_for(frame: str):
    return BuyHold if frame == "A" else PlainDCA


# ----------------------------------------------------------------------------- rolling starts
def run_rolling(ctx, prices, log=print) -> pd.DataFrame:
    """One row per (frame, rule, params, start) with the rule's and its benchmark's metrics."""
    starts = rolling_starts()
    assert horizon_end(starts[-1]) <= DEV_END, "a rolling start would reach the holdout"
    rows = []
    inst: dict = {}

    def strat(cls, p):
        k = (cls, tuple(sorted(p.items())))
        if k not in inst:
            inst[k] = cls(ctx, **p)
        return inst[k]

    for frame in ("A", "B"):
        bcls = bench_for(frame)
        bench = {s: metrics(run(strat(bcls, {}), prices, s, horizon_end(s), frame), frame) for s in starts}
        for cls, p in rules_for(frame):
            for s in starts:
                m = metrics(run(strat(cls, p), prices, s, horizon_end(s), frame), frame)
                b = bench[s]
                rows.append({"frame": frame, "rule": cls.key, "name": cls.name, "params": label(p),
                             "start": s, "multiple": m["multiple"], "bench_multiple": b["multiple"],
                             "max_dd": m["max_dd"], "bench_max_dd": b["max_dd"], "btc_per_1k": m["btc_per_1k"],
                             "bench_btc_per_1k": b["btc_per_1k"], "time_in_market": m["time_in_market"]})
            log(f"  frame {frame} {cls.key} {label(p)}: done")
    return pd.DataFrame(rows)


def label(p: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in p.items())


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    out = []
    for (frame, rule, name, params), g in df.groupby(["frame", "rule", "name", "params"], sort=False):
        diff = g["multiple"] - g["bench_multiple"]
        win = float((diff > 0).mean())
        med_dd, med_bdd = float(g["max_dd"].median()), float(g["bench_max_dd"].median())
        btc_ratio = (g["btc_per_1k"] / g["bench_btc_per_1k"]).median()
        out.append({"frame": frame, "rule": rule, "name": name, "params": params, "starts": len(g),
                    "pct_won": win, "median_diff": float(diff.median()), "worst_diff": float(diff.min()),
                    "pct_lower_dd": float((g["max_dd"] < g["bench_max_dd"]).mean()),
                    "median_dd": med_dd, "bench_median_dd": med_bdd, "median_btc_ratio": float(btc_ratio),
                    "verdict": "PASS" if win >= WIN_FRAC and med_dd < med_bdd else "FAIL"})
    return pd.DataFrame(out).sort_values(["frame", "pct_won"], ascending=[True, False]).reset_index(drop=True)
