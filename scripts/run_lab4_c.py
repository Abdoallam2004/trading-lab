"""Lab 4 phase C: derivatives / flow signals as spot event studies (BTC + ETH cross-check).
Writes reports/lab4_phaseC_events.csv, reports/lab4_phaseC_forest.png, data/lab4/results_C.pkl."""
import pickle

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import _bootstrap  # noqa: F401
from lab.config import REPORTS_DIR
from lab4.data import LAB4_DIR, load
from lab4.phaseC import HORIZONS, SIGNALS, event_study, judge

BLUE, INK, INK2, MUTED, GRID, SURFACE = "#2a78d6", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb"


def forest(t: pd.DataFrame, out):
    sigs = list(dict.fromkeys(t["signal"]))
    fig, axes = plt.subplots(1, len(HORIZONS), figsize=(14, 4.8), sharey=True, facecolor=SURFACE)
    for ax, h in zip(axes, HORIZONS):
        ax.set_facecolor(SURFACE)
        ax.grid(True, axis="x", color=GRID, linewidth=0.6)
        ax.spines[["top", "right"]].set_visible(False)
        g = t[t.horizon == h].set_index("signal").reindex(sigs)
        y = np.arange(len(sigs))
        ok = g["ci_lo"].notna()
        ax.hlines(y[ok], g["ci_lo"][ok] * 100, g["ci_hi"][ok] * 100, color=MUTED, linewidth=2)
        ax.scatter(g["mean_excess"] * 100, y, color=[BLUE if f else INK2 for f in g["fdr_pass"].fillna(False)],
                   s=36, zorder=3)
        ax.axvline(0, color=INK, linewidth=1)
        ax.set_title(f"{h}-day forward", loc="left", color=INK, fontsize=10)
        ax.set_xlabel("excess return vs same regime (%)", color=INK2, fontsize=8)
        ax.tick_params(colors=MUTED)
    axes[0].set_yticks(np.arange(len(sigs)), [f"{s} (n={int(t[(t.signal == s)].events.max())})" for s in sigs],
                       color=INK2)
    fig.suptitle("Phase C — BTC event studies: mean excess forward return with 95% block-bootstrap CI "
                 "(blue = significant after FDR 10%; none survive the ETH and regime checks)",
                 x=0.01, ha="left", color=INK, fontsize=10.5)
    fig.tight_layout()
    fig.savefig(out, dpi=130, facecolor=SURFACE)
    plt.close(fig)


def main():
    btc = load("spot_BTCUSDT_1d")
    rb, sb = event_study("BTCUSDT", btc)
    re, se = event_study("ETHUSDT", btc)
    j = judge(rb, re)
    allr = pd.concat([j.assign(asset="BTCUSDT"), re.assign(asset="ETHUSDT")], ignore_index=True)
    allr.to_csv(REPORTS_DIR / "lab4_phaseC_events.csv", index=False)
    forest(j, REPORTS_DIR / "lab4_phaseC_forest.png")
    with open(LAB4_DIR / "results_C.pkl", "wb") as fh:
        pickle.dump({"btc": j, "eth": re, "events_btc": sb, "events_eth": se}, fh)
    cols = ["signal", "horizon", "events", "mean_excess", "ci_lo", "ci_hi", "p", "fdr_pass", "right_sign",
            "eth_excess", "regimes_same_sign", "survives"]
    print(j[cols].round(4).to_string())
    print("survivors:", j[j.survives][["signal", "horizon"]].values.tolist() or "none")
    print("tests:", int(j["p"].notna().sum()), "events BTC", {k: len(v) for k, v in sb.items()},
          "ETH", {k: len(v) for k, v in se.items()}, "| D7 skipped: no Fear & Greed data")


if __name__ == "__main__":
    main()
