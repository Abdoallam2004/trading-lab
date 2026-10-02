"""Stats for the discretionary paper-trading journal (journal/trades.csv).

    python scripts/journal_stats.py [--file journal/trades.csv]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def fills_value(s) -> float:
    """'qty@price;qty@price' -> total quote value."""
    if not isinstance(s, str) or not s.strip():
        return 0.0
    total = 0.0
    for part in s.split(";"):
        q, p = part.split("@")
        total += float(q) * float(p)
    return total


def load(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    for c in ("opened_utc", "closed_utc"):
        df[c] = pd.to_datetime(df[c], utc=True, errors="coerce")
    calc = (df["exit_fills"].map(fills_value) - df["entry_fills"].map(fills_value) - df["fees_usdt"].fillna(0)) \
        / df["planned_risk_usdt"]
    df["r"] = pd.to_numeric(df.get("result_r"), errors="coerce").fillna(calc)
    return df.sort_values("closed_utc").reset_index(drop=True)


def streak(r: pd.Series) -> int:
    best = cur = 0
    for x in r:
        cur = cur + 1 if x < 0 else 0
        best = max(best, cur)
    return best


def stats(r: pd.Series) -> dict:
    r = r.dropna()
    if len(r) == 0:
        return {"trades": 0}
    gains, losses = r[r > 0].sum(), -r[r < 0].sum()
    return {"trades": len(r), "win_rate": float((r > 0).mean()), "avg_r": float(r.mean()),
            "expectancy_r": float(r.mean()), "profit_factor": float(gains / losses) if losses > 0 else np.inf,
            "avg_win_r": float(r[r > 0].mean()) if (r > 0).any() else np.nan,
            "avg_loss_r": float(r[r < 0].mean()) if (r < 0).any() else np.nan,
            "longest_losing_streak": streak(r)}


def report(df: pd.DataFrame) -> str:
    L = ["# Journal stats", ""]
    s = stats(df["r"])
    L.append(f"All trades: {s}")
    if s["trades"] < 50:
        L.append(f"(only {s['trades']} trades — too few to judge an edge; the labs needed >= 100)")
    for col in ("setup", "regime", "followed_plan"):
        if col in df:
            L.append(f"\nBy {col}:")
            for k, g in df.groupby(col):
                L.append(f"  {k}: {stats(g['r'])}")
    if "emotion" in df:
        L.append("\nBy emotion (1 calm .. 5 stressed):")
        for k, g in df.groupby("emotion"):
            L.append(f"  {k}: {stats(g['r'])}")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", type=Path, default=ROOT / "journal" / "trades.csv")
    args = ap.parse_args()
    if not args.file.exists():
        raise SystemExit(f"{args.file} not found: copy journal/trades_template.csv to start")
    print(report(load(args.file)))


if __name__ == "__main__":
    main()
