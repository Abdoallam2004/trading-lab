"""Lab 4 phase D: macro correlations, macro regime, macro size overlay on S1/S2 (rolling starts, C1).
Writes reports/lab4_phaseD_*.csv/png and data/lab4/results_D.pkl."""
import pickle

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

import _bootstrap  # noqa: F401
from lab.config import REPORTS_DIR
from lab2.strategies import DCA200W, PlainDCA, BuyHold, RegimeFilter
from lab4.data import LAB4_DIR
from lab4.macro import (S1Macro, S2Macro, conditional_forward, daily_returns, instability, monthly_10y_corr,
                        rolling_corr)
from lab4.rolling import run_rolling, summarize

BLUE, ORANGE, AQUA, INK, INK2, MUTED, GRID, SURFACE = ("#2a78d6", "#eb6834", "#1baf7a", "#0b0b0b", "#52514e",
                                                       "#898781", "#e1e0d9", "#fcfcfb")


def main():
    rc = rolling_corr(daily_returns())
    inst = instability(rc)
    y10 = monthly_10y_corr()
    cond = conditional_forward(30)
    fig, ax = plt.subplots(figsize=(12, 4.5), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.spines[["top", "right"]].set_visible(False)
    labels = {"VIX_change": "VIX daily change", "dollar_proxy": "dollar proxy (1 / EUR-USDT)",
              "gold_proxy": "gold proxy (PAXG-USDT)"}
    for color, c in zip((BLUE, ORANGE, AQUA), ["VIX_change", "dollar_proxy", "gold_proxy"]):
        s = rc[c].dropna()
        ax.plot(s.index, s, color=color, linewidth=1.8, label=labels[c])
    ax.axhline(0, color=INK, linewidth=1)
    ax.set_ylabel("90-day correlation with BTC daily return", color=INK2, fontsize=8)
    ax.set_title("Phase D-1 — rolling 90-day correlations (Nasdaq, DXY, daily 10y and Fed balance sheet are not "
                 "reachable here)", loc="left", color=INK, fontsize=10)
    ax.legend(frameon=False, fontsize=8, labelcolor=INK2)
    fig.tight_layout()
    fig.savefig(REPORTS_DIR / "lab4_phaseD_correlations.png", dpi=130, facecolor=SURFACE)
    plt.close(fig)

    a = run_rolling([("S1 20w", RegimeFilter, {"sma": "20w"}), ("S1 20w + macro", S1Macro, {"sma": "20w"})],
                    "A", BuyHold)
    b = run_rolling([("S2 aggressive", DCA200W, {"table": "aggressive"}),
                     ("S2 aggressive + macro", S2Macro, {"table": "aggressive"})], "B", PlainDCA)
    roll = pd.concat([a, b], ignore_index=True)
    summ = summarize(roll)
    # does the overlay beat the plain rule (same starts)?
    vs = []
    for frame, base, ov in (("A", "S1 20w", "S1 20w + macro"), ("B", "S2 aggressive", "S2 aggressive + macro")):
        g0 = roll[(roll.frame == frame) & (roll.rule == base)].set_index("start")
        g1 = roll[(roll.frame == frame) & (roll.rule == ov)].set_index("start")
        d = g1["multiple"] - g0["multiple"]
        vs.append({"frame": frame, "overlay": ov, "pct_starts_better_than_plain": float((d > 0).mean()),
                   "median_diff_vs_plain": float(d.median()), "median_dd_plain": float(g0["max_dd"].median()),
                   "median_dd_overlay": float(g1["max_dd"].median())})
    vs = pd.DataFrame(vs)
    inst.to_csv(REPORTS_DIR / "lab4_phaseD_correlation_stability.csv")
    cond.to_csv(REPORTS_DIR / "lab4_phaseD_macro_regime.csv", index=False)
    roll.to_csv(REPORTS_DIR / "lab4_phaseD_overlay_rolling.csv", index=False)
    with open(LAB4_DIR / "results_D.pkl", "wb") as fh:
        pickle.dump({"instability": inst, "y10": y10, "conditional": cond, "overlay": summ, "overlay_vs_plain": vs},
                    fh)
    print(inst.round(3).to_string())
    print("10y monthly:", y10)
    print(cond.round(4).to_string())
    print(summ.round(3).to_string())
    print(vs.round(3).to_string())


if __name__ == "__main__":
    main()
