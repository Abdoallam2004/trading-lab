"""Lab 3, final stage: run the LOCKED holdout (2025-10-01 .. 2026-09-30) exactly once with the
choices frozen in reports/lab3_frozen.json, then write reports/lab3_report.md.

The walk-forward simply continues: each holdout quarter uses the frozen rule set, with its
parameter set chosen on the 12 months before that quarter (same mechanical procedure).
"""
from __future__ import annotations

import hashlib
import json
import pickle
import sys

import pandas as pd

import _bootstrap  # noqa: F401
from lab.config import REPORTS_DIR
from lab3.data import HOLDOUT_END, HOLDOUT_START, LAB3_DIR
from lab3.market import Market
from lab3.report import build_markdown, final_label
from lab3.setups import SETUPS
from lab3.wf import HOLDOUT_TESTS, Lab, metrics
from lab3_notes import notes_for

OUT = REPORTS_DIR / "lab3_holdout.json"


def main():
    if OUT.exists():
        sys.exit(f"{OUT} exists: the holdout has already been run once. Refusing to run it again.")
    frozen = json.loads((REPORTS_DIR / "lab3_frozen.json").read_text())
    sha = frozen.pop("sha256")
    assert hashlib.sha256(json.dumps(frozen, indent=1, default=str).encode()).hexdigest() == sha, "frozen file edited"
    frozen["sha256"] = sha
    dev = pickle.load(open(LAB3_DIR / "dev_results.pkl", "rb"))

    lab = Lab(Market(holdout=True), log=lambda *_: None)
    hold, rows = {}, []
    for S in SETUPS:
        rules = frozen["setups"][S.key]["rules"]
        wf = lab.walk_forward(S, rules, tests=HOLDOUT_TESTS)
        m = metrics(wf.trades, (HOLDOUT_START, HOLDOUT_END))
        label = final_label(frozen["setups"][S.key]["dev_label"], m)
        hold[S.key] = {"metrics": m, "choices": wf.choices, "label": label}
        if len(wf.trades):
            rows.append(wf.trades.assign(setup=S.key))
        print(f"{S.key:<4} holdout: {m['trades']} trades, expectancy {m['expectancy']}, final label {label}")
    OUT.write_text(json.dumps({"run_at": pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds"),
                               "frozen_sha256": sha, "setups": hold}, indent=1, default=str))
    if rows:
        pd.concat(rows, ignore_index=True).to_csv(REPORTS_DIR / "lab3_holdout_trades.csv", index=False)
    notes = notes_for(dev, hold, frozen)
    (REPORTS_DIR / "lab3_report.md").write_text(build_markdown(dev, hold, frozen, notes))
    print("report ->", REPORTS_DIR / "lab3_report.md")


if __name__ == "__main__":
    main()
