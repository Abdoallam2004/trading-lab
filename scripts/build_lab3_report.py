"""Rebuild reports/lab3_report.md (and the Part A charts) from saved results only.

Reads data/lab3/dev_results.pkl, reports/lab3_frozen.json, reports/lab3_holdout.json and
reports/lab3_partA_rolling.csv. Loads no market data, so it cannot re-run or peek at the holdout.
"""
import json
import pickle

import pandas as pd

import _bootstrap  # noqa: F401
from lab.config import REPORTS_DIR
from lab3.data import LAB3_DIR
from lab3.report import build_markdown, charts_partA
from lab3_notes import notes_for


def main():
    dev = pickle.load(open(LAB3_DIR / "dev_results.pkl", "rb"))
    frozen = json.loads((REPORTS_DIR / "lab3_frozen.json").read_text())
    hold = json.loads((REPORTS_DIR / "lab3_holdout.json").read_text())["setups"]
    for h in hold.values():
        h["metrics"] = {k: (float(v) if isinstance(v, (int, float)) else v) for k, v in h["metrics"].items()}
        h["metrics"]["trades"] = int(h["metrics"]["trades"])
    rolling = pd.read_csv(REPORTS_DIR / "lab3_partA_rolling.csv", parse_dates=["start"])
    charts_partA(rolling[rolling.costs == "1x"], dev["part_a"]["1x"], REPORTS_DIR)
    (REPORTS_DIR / "lab3_report.md").write_text(build_markdown(dev, hold, frozen, notes_for(dev, hold, frozen)))
    print("rebuilt", REPORTS_DIR / "lab3_report.md")


if __name__ == "__main__":
    main()
