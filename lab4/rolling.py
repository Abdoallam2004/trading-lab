"""Rolling-start evaluation (Lab 3 Part A method) for Lab 4's accumulation rules, under C1 costs.

57 starts (first Monday of each month 2018-01 .. 2022-09), 3-year runs ending by 2025-09-30.
C1 for accumulation = limit buys at the Monday open: 0.075% fee, no slippage.
"""
from __future__ import annotations

import contextlib

import pandas as pd

import lab2.sim as l2sim
from lab2.sim import metrics, run
from lab3.partA import build_context, horizon_end, rolling_starts


@contextlib.contextmanager
def costs(fee: float, slip: float):
    old = (l2sim.FEE, l2sim.SLIP)
    l2sim.FEE, l2sim.SLIP = fee, slip
    try:
        yield
    finally:
        l2sim.FEE, l2sim.SLIP = old


def run_rolling(items, frame: str, bench, fee=0.00075, slip=0.0, ctx=None, prices=None, extra=None) -> pd.DataFrame:
    """items = [(label, cls, params)]. `extra` = {label: fn(start, end) -> RunResult-like dict of metrics}."""
    if ctx is None:
        ctx, prices = build_context()
    rows = []
    inst = {}
    with costs(fee, slip):
        for s in rolling_starts():
            e = horizon_end(s)
            b = metrics(run(bench(ctx), prices, s, e, frame), frame)
            for label, cls, p in items:
                if label not in inst:
                    inst[label] = cls(ctx, **p)
                m = metrics(run(inst[label], prices, s, e, frame), frame)
                rows.append(_row(frame, label, s, m, b))
            for label, fn in (extra or {}).items():
                rows.append(_row(frame, label, s, fn(s, e), b))
    return pd.DataFrame(rows)


def _row(frame, label, s, m, b):
    return {"frame": frame, "rule": label, "start": s, "multiple": m["multiple"], "bench_multiple": b["multiple"],
            "max_dd": m["max_dd"], "bench_max_dd": b["max_dd"], "btc_per_1k": m.get("btc_per_1k"),
            "bench_btc_per_1k": b.get("btc_per_1k"), **{k: m[k] for k in m if k.startswith("x_")}}


def summarize(df: pd.DataFrame, win_frac: float = 0.60) -> pd.DataFrame:
    out = []
    for (frame, rule), g in df.groupby(["frame", "rule"], sort=False):
        diff = g["multiple"] - g["bench_multiple"]
        md, mb = g["max_dd"].median(), g["bench_max_dd"].median()
        win = float((diff > 0).mean())
        out.append({"frame": frame, "rule": rule, "starts": len(g), "pct_won": win, "median_diff": diff.median(),
                    "worst_diff": diff.min(), "pct_lower_dd": float((g["max_dd"] < g["bench_max_dd"]).mean()),
                    "median_dd": md, "bench_median_dd": mb,
                    "verdict": "PASS" if win >= win_frac and md < mb else "FAIL"})
    return pd.DataFrame(out)
