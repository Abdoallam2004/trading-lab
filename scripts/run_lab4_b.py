"""Lab 4 phase B: Lab 3 setups with the user's real execution. Saves data/lab4/results_B.pkl and
reports/lab4_phaseB_grid.csv (every configuration)."""
import pickle
import time

import numpy as np
import pandas as pd

import _bootstrap  # noqa: F401
from lab.config import REPORTS_DIR
from lab3.market import Market
from lab3.wf import metrics
from lab4.data import LAB4_DIR
from lab4.execution import C0, C1, C2, EXEC_GRID, Exec, Scenario
from lab4.phaseB import SETUPS_B, LabB, T6BaseCrack, frozen_rules, random_baseline

ZERO = Scenario("zero", 0.0, 0.0, 0.0)


def main():
    t0 = time.time()
    m = Market()
    lab = LabB(m)
    fr = frozen_rules()
    rows, best = [], {}
    for S in SETUPS_B:
        rules = fr[S.key]
        execs = [Exec()] if S is T6BaseCrack else EXEC_GRID   # T6 keeps its own ladder and base exit
        res = {}
        for ex in execs:
            for sc in (C0, C1, C2):
                wf = lab.walk_forward(S, rules, ex, sc)
                mt = metrics(wf.trades, wf.span)
                res[(ex, sc.name)] = wf
                rows.append({"setup": S.key, "exec": ex.label if S is not T6BaseCrack else "own ladder",
                             "entry": ex.entry, "exit": ex.exit, "stop": ex.stop, "scenario": sc.name,
                             "trades": mt["trades"], "expectancy": mt["expectancy"], "pf": mt["profit_factor"],
                             "months_up": mt["pct_months_up"], "max_dd": mt["max_dd"]})
        # best execution variant per setup = highest OOS expectancy under C2 (selection on OOS -> counted in DSR)
        ex_b = max(execs, key=lambda e: res[(e, "C2")].expectancy)
        wf2 = res[(ex_b, "C2")]
        out = {"exec": ex_b, "rules": rules, "C0": res[(ex_b, "C0")], "C1": res[(ex_b, "C1")], "C2": wf2}
        out["touch_C1"] = lab.walk_forward(S, rules, ex_b, C1, fill="touch")
        out["zero"] = lab.walk_forward(S, rules, ex_b, ZERO, choices=wf2.choices)
        out["eth_C2"] = lab.walk_forward(S, rules, ex_b, C2, asset="ETHUSDT", choices=wf2.choices)
        if S is T6BaseCrack:
            out["rand"] = np.array([])   # T6's 4-tranche ladder has no single-entry random analogue here
        else:
            out["rand"] = random_baseline(lab, S, rules, wf2, ex_b, C2)
        best[S.key] = out
        print(f"{S.key:<4} best {ex_b.label:<12} C2 {wf2.expectancy:+.3f}R n={len(wf2.trades)} "
              f"C1 {out['C1'].expectancy:+.3f} C0 {out['C0'].expectancy:+.3f} zero {out['zero'].expectancy:+.3f} "
              f"ETH {out['eth_C2'].expectancy:+.3f} ({time.time() - t0:.0f}s)")
    grid = pd.DataFrame(rows)
    grid.to_csv(REPORTS_DIR / "lab4_phaseB_grid.csv", index=False)
    with open(LAB4_DIR / "results_B.pkl", "wb") as fh:
        pickle.dump({"grid": grid, "best": best, "registry": lab.registry}, fh)
    print(f"phase B done in {time.time() - t0:.0f}s; {len(lab.registry)} configurations evaluated")


if __name__ == "__main__":
    main()
