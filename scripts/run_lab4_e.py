"""Lab 4 phase E: accumulation upgrades (rolling 3-year starts, C1 costs).
Writes reports/lab4_phaseE_*.csv/png and data/lab4/results_E.pkl."""
import pickle
import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import _bootstrap  # noqa: F401
from lab.config import REPORTS_DIR
from lab2.sim import metrics, run, twr_returns
from lab2.strategies import BuyHold, DCA200W, PlainDCA
from lab3.partA import build_context, horizon_end, rolling_starts
from lab4.data import LAB4_DIR
from lab4.ladder import L1_GRID, L2_LADDER, Hourly, S2Crowding, ladder
from lab4.rolling import costs, run_rolling, summarize

BLUE, INK, INK2, MUTED, GRID, SURFACE, BAND = ("#2a78d6", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb",
                                               "#dddcd5")


def label(p):
    return f"L1 g={p['g']:.0%} N={p['n']} tp={p['tp']}"


def main():
    t0 = time.time()
    ctx, prices = build_context()
    hb = Hourly()
    starts = rolling_starts()
    rows = []
    with costs(0.00075, 0.0):
        b1, b2, s2 = BuyHold(ctx), PlainDCA(ctx), DCA200W(ctx, table="aggressive")
        for s in starts:
            e = horizon_end(s)
            ref = {}
            for name, strat in (("B1", b1), ("B2", b2), ("S2", s2)):
                r = run(strat, prices, s, e, "A")
                ref[name] = (metrics(r, "A"), r)
            for name, (m, _) in ref.items():
                rows.append({"start": s, "rule": name, "multiple": m["multiple"], "max_dd": m["max_dd"],
                             "btc_per_1k": m["btc_per_1k"], "utilization": m["exposure"]})
            for p in L1_GRID:
                m = ladder(hb, s, e, **p)
                rows.append({"start": s, "rule": label(p), "multiple": m["multiple"], "max_dd": m["max_dd"],
                             "btc_per_1k": m["btc_per_1k"], "utilization": m["x_utilization"],
                             "longest_underwater_days": m["x_longest_underwater_days"],
                             "round_trips": m["x_round_trips"]})
            # L2: 80% S2 + 20% the pre-declared ladder (lots scale linearly with capital)
            lad = ladder(hb, s, e, **L2_LADDER)["equity"]
            s2eq = ref["S2"][1].equity
            comb = (0.8 * s2eq + 0.2 * lad.reindex(s2eq.index, method="ffill")).dropna()
            rows.append({"start": s, "rule": "L2 80% S2 + 20% L1", "multiple": float(comb.iloc[-1] / 10_000),
                         "max_dd": float((1 - comb / np.maximum(comb.cummax(), 10_000)).max()), "btc_per_1k": np.nan,
                         "utilization": np.nan})
    df = pd.DataFrame(rows)
    piv = {k: df[df.rule == k].set_index("start") for k in df.rule.unique()}
    summ = []
    for rule, g in piv.items():
        if rule in ("B1", "B2", "S2"):
            continue
        rec = {"rule": rule}
        for bname in ("B1", "B2", "S2"):
            bb = piv[bname]
            d = g["multiple"] - bb["multiple"]
            rec[f"won_vs_{bname}"] = float((d > 0).mean())
            rec[f"median_diff_vs_{bname}"] = float(d.median())
        rec["median_dd"] = float(g["max_dd"].median())
        rec["median_dd_B1"] = float(piv["B1"]["max_dd"].median())
        rec["median_dd_B2"] = float(piv["B2"]["max_dd"].median())
        rec["median_utilization"] = float(g["utilization"].median()) if g["utilization"].notna().any() else np.nan
        rec["max_underwater_days"] = float(g["longest_underwater_days"].max()) if "longest_underwater_days" in g else np.nan
        rec["median_round_trips"] = float(g["round_trips"].median()) if "round_trips" in g else np.nan
        rec["verdict_vs_B1"] = "PASS" if rec["won_vs_B1"] >= 0.6 and rec["median_dd"] < rec["median_dd_B1"] else "FAIL"
        summ.append(rec)
    summ = pd.DataFrame(summ).sort_values("won_vs_B1", ascending=False)

    # L3 (weekly frame B): S2 with crowding overlay vs B2 and vs plain S2
    l3 = run_rolling([("S2 aggressive", DCA200W, {"table": "aggressive"}),
                      ("L3 S2 + crowding", S2Crowding, {"table": "aggressive"})], "B", PlainDCA, ctx=ctx, prices=prices)
    l3s = summarize(l3)
    g0 = l3[l3.rule == "S2 aggressive"].set_index("start")
    g1 = l3[l3.rule == "L3 S2 + crowding"].set_index("start")
    d = (g1["multiple"] - g0["multiple"])
    later = d[d.index >= pd.Timestamp("2020-12-01", tz="UTC")]
    l3_vs = {"pct_better_than_S2_all": float((d > 0).mean()), "pct_better_than_S2_from_2020_12": float((later > 0).mean()),
             "pct_equal": float((d.abs() < 1e-9).mean()), "median_diff_from_2020_12": float(later.median()),
             "starts_from_2020_12": len(later)}

    df.to_csv(REPORTS_DIR / "lab4_phaseE_rolling.csv", index=False)
    summ.to_csv(REPORTS_DIR / "lab4_phaseE_summary.csv", index=False)
    # chart: % of starts won vs B1 and vs B2 per rule
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5), facecolor=SURFACE, sharey=True)
    s_ = summ.sort_values("won_vs_B1")
    for ax, col, title in zip(axes, ("won_vs_B1", "won_vs_B2"), ("vs B1 buy & hold", "vs B2 DCA ($10k over 2 years)")):
        ax.set_facecolor(SURFACE)
        ax.grid(True, axis="x", color=GRID, linewidth=0.6)
        ax.spines[["top", "right"]].set_visible(False)
        ax.barh(s_["rule"], s_[col] * 100, color=[BLUE if v >= 0.6 else BAND for v in s_[col]], height=0.7)
        ax.axvline(60, color=INK, linestyle="--", linewidth=1.2)
        for y, v in enumerate(s_[col]):
            ax.text(v * 100 + 1, y, f"{v:.0%}", va="center", fontsize=7.5, color=INK2)
        ax.set_xlim(0, 105)
        ax.set_title(f"% of 57 rolling 3-year starts won {title}", loc="left", color=INK, fontsize=9.5)
        ax.tick_params(colors=MUTED, labelsize=8)
    fig.suptitle("Phase E — accumulation upgrades, lump sum $10,000, C1 costs (blue = ≥ 60% of starts)",
                 x=0.01, ha="left", color=INK, fontsize=11)
    fig.tight_layout()
    fig.savefig(REPORTS_DIR / "lab4_phaseE_winrate.png", dpi=130, facecolor=SURFACE)
    plt.close(fig)
    with open(LAB4_DIR / "results_E.pkl", "wb") as fh:
        pickle.dump({"summary": summ, "l3": l3s, "l3_vs": l3_vs, "rolling": df}, fh)
    pd.set_option("display.width", 250)
    print(summ.round(3).to_string())
    print(l3s.round(3).to_string())
    print(l3_vs)
    print(f"phase E done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
