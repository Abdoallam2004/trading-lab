"""Lab 3, development stage (no holdout data is loaded here).

    python scripts/lab3_download.py      # once
    python scripts/run_lab3.py           # Part A + Part B on 2018/2020 .. 2025-09-30, then FREEZE
    python scripts/run_lab3_holdout.py   # exactly once: the locked 2025-10 .. 2026-09 holdout + report

Writes reports/lab3_frozen.json (every choice, fixed before the holdout), CSVs and charts,
and data/lab3/dev_results.pkl (inputs for the final report).
"""
from __future__ import annotations

import hashlib
import json
import pickle
import time

import numpy as np
import pandas as pd

import _bootstrap  # noqa: F401
import lab2.sim as l2sim
from lab.config import REPORTS_DIR
from lab3 import partA
from lab3.data import DEV_END, LAB3_DIR
from lab3.engine import Costs
from lab3.market import Market
from lab3.report import charts_partA, charts_partB, dev_checks
from lab3.setups import SETUPS
from lab3.wf import (DEV_START, DEV_TESTS, Lab, ablation, btc_buy_hold, deflated_sharpe, metrics,
                     random_baseline, test_end)

N_SIMS = 1000


def is_trades(lab, S, wf):
    parts = []
    for w, (ts, p) in enumerate(zip(wf.windows, wf.choices)):
        if p is None:
            continue
        t = lab.trades(S, "BTCUSDT", p, wf.rules)
        parts.append(t[(t["entry_time"] >= ts - pd.DateOffset(months=12)) & (t["entry_time"] < ts)])
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["r", "ret"])


def run_part_a(log):
    ctx, prices = partA.build_context()
    out = {}
    for label, fee, slip in (("1x", 0.001, 0.0005), ("2x", 0.002, 0.001)):
        l2sim.FEE, l2sim.SLIP = fee, slip
        t0 = time.time()
        df = partA.run_rolling(ctx, prices, log=lambda *_: None)
        out[label] = (df, partA.summarize(df))
        log(f"Part A rolling starts at {label} costs: {time.time() - t0:.0f}s")
    l2sim.FEE, l2sim.SLIP = 0.001, 0.0005
    gate = partA.gate_components(ctx.sig_price, ctx.mvrv)
    return out, gate


def main():
    log = print
    t0 = time.time()
    part_a, gate = run_part_a(log)
    m = Market()
    lab = Lab(m, log=log)
    res = {}
    for S in SETUPS:
        t1 = time.time()
        ab = ablation(lab, S)
        final = ab["results"][ab["final_rules"]]
        eth = lab.walk_forward(S, final.rules, asset="ETHUSDT", choices=final.choices)
        x2 = lab.walk_forward(S, final.rules, costs=Costs().doubled(), choices=final.choices)
        gross = lab.walk_forward(S, final.rules, costs=Costs(0.0, 0.0), choices=final.choices)  # diagnostic only
        it = is_trades(lab, S, final)
        exps, R = random_baseline(lab, S, final, n_sims=N_SIMS)
        res[S.key] = {"ablation": ab, "final": final, "eth": eth, "x2": x2, "gross": gross, "is_trades": it,
                      "rand_exp": exps, "rand_R": R}
        log(f"{S.key:<4} final rules {final.rules}: OOS {len(final.trades)} trades, "
            f"exp {final.expectancy:+.3f}R ({time.time() - t1:.0f}s)")

    srs = np.array([v["sr"] for v in lab.registry.values() if v["n"] >= 30 and np.isfinite(v["sr"])])
    n_trials = len(lab.registry) + sum(len(s) for _, s in [part_a["1x"]])
    sr_var = float(srs.var(ddof=1))
    for k, r in res.items():
        f = r["final"]
        r["oos"] = metrics(f.trades, f.span)
        r["is"] = metrics(r["is_trades"], (DEV_START, DEV_END))
        r["eth_m"] = metrics(r["eth"].trades, r["eth"].span)
        r["x2_m"] = metrics(r["x2"].trades, r["x2"].span)
        r["gross_m"] = metrics(r["gross"].trades, r["gross"].span)
        r["bh"] = btc_buy_hold(m, f.span)
        tr_exp = np.nanmean([e for e in f.train_exp if np.isfinite(e)]) if any(np.isfinite(f.train_exp)) else np.nan
        r["degradation"] = f.expectancy / tr_exp if np.isfinite(tr_exp) and tr_exp > 0 and len(f.trades) else np.nan
        r["rand_pct"] = float((r["rand_exp"] < f.expectancy).mean() * 100) if len(r["rand_exp"]) else np.nan
        r["dsr"] = deflated_sharpe(f.trades["r"].to_numpy(), n_trials, sr_var) if len(f.trades) else np.nan
        r["checks"], r["dev_label"] = dev_checks(r)
        r["spec_m"] = metrics(r["ablation"]["results"][r["ablation"]["spec_rules"]].trades, f.span)

    frozen = {
        "frozen_at": pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds"),
        "dev_end": str(DEV_END), "holdout": "2025-10-01 .. 2026-09-30 (not loaded before this file existed)",
        "n_trials_for_dsr": n_trials, "sr_variance_across_trials": sr_var,
        "walk_forward": {"train_months": 12, "test_months": 3, "min_train_trades": 30,
                         "selection": "max expectancy in R on BTC, 1x costs"},
        "setups": {k: {"rules": list(r["final"].rules), "spec_rules": list(r["ablation"]["spec_rules"]),
                       "grid": next(S for S in SETUPS if S.key == k).grid(),
                       "dev_label": r["dev_label"], "dev_oos_expectancy": r["oos"]["expectancy"],
                       "dev_oos_trades": r["oos"]["trades"],
                       "last_dev_choice": next((c for c in reversed(r["final"].choices) if c), None)}
                   for k, r in res.items()},
    }
    blob = json.dumps(frozen, indent=1, default=str)
    frozen["sha256"] = hashlib.sha256(blob.encode()).hexdigest()
    REPORTS_DIR.mkdir(exist_ok=True)
    (REPORTS_DIR / "lab3_frozen.json").write_text(json.dumps(frozen, indent=1, default=str))

    # CSVs and dev-period charts (no holdout data exists in this process)
    a1 = pd.concat([df.assign(costs=c) for c, (df, _) in part_a.items()])
    a1.to_csv(REPORTS_DIR / "lab3_partA_rolling.csv", index=False)
    trades = pd.concat([r[x].trades.assign(setup=k, run=x) for k, r in res.items() for x in ("final", "eth", "x2")
                        if len(r[x].trades)], ignore_index=True)
    trades.to_csv(REPORTS_DIR / "lab3_trades.csv", index=False)
    eq = []
    for k, r in res.items():
        t = r["final"].trades.sort_values("exit_time")
        if len(t):
            eq.append(pd.DataFrame({"setup": k, "exit_time": t["exit_time"], "cum_r": t["r"].cumsum(),
                                    "equity": np.cumprod(1 + t["ret"].to_numpy())}))
    pd.concat(eq).to_csv(REPORTS_DIR / "lab3_equity.csv", index=False)
    charts_partA(part_a["1x"][0], part_a["1x"][1], REPORTS_DIR)
    charts_partB(res, REPORTS_DIR)

    with open(LAB3_DIR / "dev_results.pkl", "wb") as fh:
        pickle.dump({"part_a": {c: s for c, (_, s) in part_a.items()}, "gate": gate.describe().to_dict(),
                     "res": {k: {x: v for x, v in r.items() if x not in ("rand_R",)} for k, r in res.items()},
                     "frozen": frozen, "registry_size": len(lab.registry)}, fh)
    print(f"frozen -> {REPORTS_DIR / 'lab3_frozen.json'} (sha256 {frozen['sha256'][:12]}); {time.time() - t0:.0f}s")
    for k, r in res.items():
        print(f"{k:<4} {r['dev_label']:<13} exp {r['oos']['expectancy']:+.3f}R n={r['oos']['trades']} "
              f"PF {r['oos']['profit_factor']:.2f} rand {r['rand_pct']:.0f}th DSR {r['dsr']:.2f} "
              f"ETH {r['eth_m']['expectancy']:+.3f} 2x {r['x2_m']['expectancy']:+.3f}")


if __name__ == "__main__":
    main()
