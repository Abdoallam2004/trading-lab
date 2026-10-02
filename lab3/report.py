"""Lab 3 checks, charts and the final markdown report."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
INK, INK2, MUTED, GRID, AXIS, SURFACE, BAND = ("#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb",
                                               "#dddcd5")


# ----------------------------------------------------------------------------- pass rules
def dev_checks(r: dict):
    """All development-period pass rules (the holdout rule is applied later)."""
    o, f = r["oos"], r["final"]
    share_1d = float((f.trades["tf"] == "1d").mean()) if len(f.trades) else 0.0
    min_n = 40 if share_1d >= 0.5 else 100
    checks = [
        ("OOS expectancy > 0.10R", o["expectancy"] > 0.10 if o["trades"] else False, f"{o['expectancy']:+.3f}R"),
        ("profit factor > 1.2", o["profit_factor"] > 1.2 if o["trades"] else False, f"{o['profit_factor']:.2f}"),
        (f"≥ {min_n} OOS trades", o["trades"] >= min_n, f"{o['trades']}"),
        ("above 95th pct of random entries", r["rand_pct"] > 95, f"{r['rand_pct']:.0f}th"),
        ("Deflated Sharpe > 0.95", bool(np.isfinite(r["dsr"]) and r["dsr"] > 0.95), f"{r['dsr']:.2f}"),
        ("ETH cross-check expectancy > 0", (r["eth_m"]["expectancy"] or -1) > 0 if r["eth_m"]["trades"] else False,
         f"{r['eth_m']['expectancy']:+.3f}R ({r['eth_m']['trades']} tr)"),
        ("positive at 2x costs", (r["x2_m"]["expectancy"] or -1) > 0 if r["x2_m"]["trades"] else False,
         f"{r['x2_m']['expectancy']:+.3f}R"),
        ("≥ 60% profitable months", (o["pct_months_up"] or 0) >= 0.60, f"{o['pct_months_up']:.0%}"),
    ]
    failed = [c for c in checks if not c[1]]
    if not failed:
        label = "DEV-PASS"
    elif len(failed) == 1 and "OOS trades" in failed[0][0]:
        label = "INCONCLUSIVE"
    else:
        label = "FAIL"
    return checks, label


def final_label(dev_label: str, hold: dict) -> str:
    if dev_label == "DEV-PASS":
        return "PASS" if hold["trades"] and hold["expectancy"] > 0 else "FAIL"
    return dev_label


# ----------------------------------------------------------------------------- charts
def _style(ax):
    ax.set_facecolor(SURFACE)
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.spines[["top", "right"]].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(AXIS)
    ax.tick_params(colors=MUTED)


def charts_partA(rolling: pd.DataFrame, summary: pd.DataFrame, out: Path):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9})
    fig, axes = plt.subplots(1, 2, figsize=(12, 8), facecolor=SURFACE)
    for ax, frame, title in zip(axes, ("A", "B"), ("Lump sum vs B1 buy & hold", "Weekly $100 vs B2 plain DCA")):
        _style(ax)
        s = summary[summary.frame == frame].sort_values("pct_won")
        labels = [f"{r} {p}" for r, p in zip(s.rule, s.params)]
        colors = [BLUE if v == "PASS" else BAND for v in s.verdict]
        ax.barh(labels, s.pct_won * 100, color=colors, height=0.7)
        ax.axvline(60, color=INK, linewidth=1.2, linestyle="--")
        ax.text(60.5, len(s) - 0.4, "60% bar", color=INK2, fontsize=8, va="top")
        for y, (v, w) in enumerate(zip(s.pct_won, s.verdict)):
            ax.text(v * 100 + 1, y, f"{v:.0%}" + ("  PASS" if w == "PASS" else ""), va="center", fontsize=7.5,
                    color=INK2)
        ax.set_xlim(0, 110)
        ax.set_xlabel("% of 57 rolling 3-year starts where the rule beat the benchmark (value ÷ contributed)",
                      color=INK2, fontsize=8)
        ax.set_title(f"Frame {frame}: {title}", loc="left", color=INK, fontsize=10)
        ax.tick_params(axis="y", labelsize=7.5, colors=INK2)
    fig.suptitle("Part A — rolling-start win rate (blue = passes: ≥ 60% of starts and lower median drawdown)",
                 x=0.01, ha="left", color=INK, fontsize=11)
    fig.tight_layout()
    fig.savefig(out / "lab3_partA_winrate.png", dpi=130, facecolor=SURFACE)
    plt.close(fig)

    # difference by start date for the best 4 rules per frame
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), facecolor=SURFACE, sharex=True)
    for ax, frame in zip(axes, ("A", "B")):
        _style(ax)
        top = summary[summary.frame == frame].head(4)
        for color, (_, row) in zip((BLUE, ORANGE, AQUA, YELLOW), top.iterrows()):
            g = rolling[(rolling.frame == frame) & (rolling.rule == row.rule) & (rolling.params == row.params)]
            ax.plot(g.start, g.multiple - g.bench_multiple, color=color, linewidth=2, label=f"{row.rule} {row.params}")
        ax.axhline(0, color=INK, linewidth=1)
        ax.set_ylabel("value÷contributed minus benchmark's", color=INK2, fontsize=8)
        bench = "B1 buy & hold" if frame == "A" else "B2 plain DCA"
        ax.set_title(f"Frame {frame}: best four rules vs {bench}, by start date (each run lasts 3 years)",
                     loc="left", color=INK, fontsize=10)
        ax.legend(frameon=False, fontsize=8, labelcolor=INK2, loc="upper right")
    fig.tight_layout()
    fig.savefig(out / "lab3_partA_by_start.png", dpi=130, facecolor=SURFACE)
    plt.close(fig)


def charts_partB(res: dict, out: Path):
    keys = list(res)
    cols = 4
    rows = int(np.ceil(len(keys) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(14, 3.6 * rows), facecolor=SURFACE)
    for ax in axes.flat:
        ax.set_visible(False)
    for ax, k in zip(axes.flat, keys):
        ax.set_visible(True)
        _style(ax)
        r = res[k]
        t = r["final"].trades
        if len(t) == 0:
            ax.text(0.5, 0.5, "no OOS trades", ha="center", va="center", color=INK2, transform=ax.transAxes)
            ax.set_title(k, loc="left", color=INK, fontsize=10)
            continue
        R = r["rand_R"]
        order = np.argsort(t["exit_time"].to_numpy())
        x = np.arange(1, len(t) + 1)
        cum_rand = np.nancumsum(R[:, order], axis=1)
        lo, mid, hi = np.percentile(cum_rand, [5, 50, 95], axis=0)
        ax.fill_between(x, lo, hi, color=BAND, linewidth=0, label="random entries 5–95%")
        ax.plot(x, mid, color=MUTED, linewidth=1, label="random median")
        ax.plot(x, t["r"].to_numpy()[order].cumsum(), color=BLUE, linewidth=2, label=k)
        ax.axhline(0, color=AXIS, linewidth=0.8)
        ax.set_title(f"{k}: {r['oos']['expectancy']:+.2f}R/trade, {r['rand_pct']:.0f}th pct", loc="left",
                     color=INK, fontsize=9.5)
        ax.set_xlabel("OOS trade #", color=INK2, fontsize=8)
        ax.set_ylabel("cumulative R", color=INK2, fontsize=8)
    axes.flat[0].legend(frameon=False, fontsize=7.5, labelcolor=INK2, loc="lower left")
    fig.suptitle("Part B — stitched walk-forward OOS (2021-01 → 2025-09, BTC) vs 1,000 random-entry runs",
                 x=0.01, ha="left", color=INK, fontsize=11)
    fig.tight_layout()
    fig.savefig(out / "lab3_partB_oos_vs_random.png", dpi=130, facecolor=SURFACE)
    plt.close(fig)


# ----------------------------------------------------------------------------- markdown
def f(x, kind="num"):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "–"
    return {"pct": f"{x:.1%}", "r": f"{x:+.3f}R", "x": f"{x:+.2f}", "int": f"{int(x)}", "num": f"{x:.2f}"}[kind]


def table(headers, rows) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    return "\n".join(out + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


MCOLS = [("Trades", "trades", "int"), ("Win", "win_rate", "pct"), ("Avg win", "avg_win_r", "num"),
         ("Avg loss", "avg_loss_r", "num"), ("Expectancy", "expectancy", "r"), ("PF", "profit_factor", "num"),
         ("CAGR", "cagr", "pct"), ("Max DD", "max_dd", "pct"), ("Exposure", "exposure", "pct"),
         ("Months up", "pct_months_up", "pct"), ("Lose streak", "streak_trades", "int"),
         ("…days", "streak_days", "int")]


def mrow(m):
    return [f(m.get(k), kind) for _, k, kind in MCOLS]


SETUP_DOCS = {}


def _setup_doc(key):
    from .setups import SETUPS
    S = next(s for s in SETUPS if s.key == key)
    return S


def build_markdown(dev: dict, hold: dict, frozen: dict, notes: dict) -> str:
    res, part_a = dev["res"], dev["part_a"]
    L = ["# Lab 3 — fair re-test of long-horizon rules + 6 short-term halal setups\n", "## Verdict\n",
         notes["verdict"] + "\n"]

    # ------------------------------------------------------------------ rankings
    L.append("## Ranking — Part A (rolling 3-year starts, by % of starts won)\n")
    L.append("57 starts (first Monday of each month, 2018-01 → 2022-09), each run 3 years, all ending by 2025-09-30. "
             "**Pass = beats the benchmark on final value ÷ money contributed in ≥ 60% of starts AND has a lower median "
             "max drawdown.** Lab 2's parameter grids are used unchanged; every grid member is shown (nothing selected).\n")
    for frame, title in (("A", "Frame A — lump sum $10,000 vs B1 buy & hold"),
                         ("B", "Frame B — $100 every Monday vs B2 plain weekly DCA")):
        s1, s2 = part_a["1x"], part_a["2x"]
        s1 = s1[s1.frame == frame]
        rows = []
        for _, r in s1.iterrows():
            r2 = s2[(s2.frame == frame) & (s2.rule == r.rule) & (s2.params == r.params)].iloc[0]
            rows.append([f"**{r.rule}** {r['name']}", f"`{r.params}`", f"{r.pct_won:.0%}", f"{r.median_diff:+.2f}",
                         f"{r.worst_diff:+.2f}", f"{r.pct_lower_dd:.0%}", f"{r.median_dd:.0%} vs {r.bench_median_dd:.0%}",
                         f"{r.median_btc_ratio:.2f}×", verdict_md(r.verdict), f"{r2.pct_won:.0%} {verdict_md(r2.verdict)}"])
        L.append(f"### {title}\n")
        L.append(table(["Rule", "Params", "Starts won", "Median Δ value÷contrib.", "Worst Δ", "Starts with lower DD",
                        "Median max DD (rule vs bench)", "Median BTC per $ vs bench", "Verdict", "At 2× costs"], rows))
        L.append("")
    L.append("![Part A win rates](lab3_partA_winrate.png)\n")
    L.append("![Part A by start date](lab3_partA_by_start.png)\n")

    L.append("## Ranking — Part B (stitched walk-forward OOS on BTC, by expectancy)\n")
    L.append("Walk-forward 2020-01 → 2025-09: train 12 months / test 3 months, rolling; parameters chosen in each train "
             "window by expectancy in R (≥ 30 train trades). OOS = the 19 stitched test quarters 2021-01 → 2025-09. "
             "The holdout (2025-10 → 2026-09) was run once, after `reports/lab3_frozen.json` was committed.\n")
    order = sorted(res, key=lambda k: -(res[k]["oos"]["expectancy"] if res[k]["oos"]["trades"] else -9))
    rows = []
    for k in order:
        r, h = res[k], hold[k]
        rows.append([f"**{k}** {_setup_doc(k).name}", f"`{', '.join(r['final'].rules) or 'bare trigger'}`",
                     r["oos"]["trades"], f(r["oos"]["expectancy"], "r"), f(r["oos"]["profit_factor"]),
                     f"{r['rand_pct']:.0f}th", f(r["dsr"]), f(r["eth_m"]["expectancy"], "r"),
                     f(r["x2_m"]["expectancy"], "r"), f(r["oos"]["pct_months_up"], "pct"),
                     f"{f(h['metrics']['expectancy'], 'r')} ({h['metrics']['trades']})", verdict_md(h["label"])])
    L.append(table(["Setup", "Rules kept", "OOS trades", "Expectancy", "PF", "vs random", "DSR", "ETH", "2× costs",
                    "Months up", "Holdout (trades)", "Verdict"], rows))
    L.append("\n![Part B OOS vs random entries](lab3_partB_oos_vs_random.png)\n")

    # ------------------------------------------------------------------ Part A detail
    L.append("## Part A details\n")
    L += [f"- {x}" for x in notes["part_a"]]
    L.append("")

    # ------------------------------------------------------------------ Part B detail
    L.append("## Part B — per setup\n")
    L.append(f"Deflated Sharpe uses **{frozen['n_trials_for_dsr']} configurations** (every setup × rule variant × "
             f"parameter set evaluated in the ablation, plus the {frozen['n_trials_for_dsr'] - dev['registry_size']} "
             f"Part A rule/frame configurations) and the variance of per-trade Sharpe across them "
             f"({frozen['sr_variance_across_trials']:.4f}).\n")
    for k in res:
        r, h, S = res[k], hold[k], _setup_doc(k)
        L.append(f"### {k} — {S.name}\n")
        L.append(" ".join((S.__doc__ or "").split()) + "\n")
        L.append(f"Grid ({len(S.grid())} sets): `{S.GRID}` · rules as specified: `{list(r['ablation']['spec_rules'])}` "
                 f"· rules kept by the ablation: `{list(r['final'].rules) or 'none (bare trigger)'}`\n")
        L.append("**Ablation ladder** (OOS expectancy after each step; a rule is kept only if it improves it)\n")
        L.append(table(["Step", "Rules", "OOS trades", "OOS expectancy", "Kept"],
                       [[s["step"], f"`{', '.join(s['rules']) or '–'}`", s["trades"], f(s["expectancy"], "r"),
                         "✅" if s["kept"] else "–"] for s in r["ablation"]["steps"]]))
        L.append("")
        span = r["final"].span
        rows = [["Walk-forward OOS (BTC)", f"{span[0]:%Y-%m}→{span[1]:%Y-%m}"] + mrow(r["oos"]),
                ["In-sample (train windows, chosen sets)", "2020→2025"] + mrow(r["is"]),
                ["ETH, BTC-chosen parameters", ""] + mrow(r["eth_m"]),
                ["2× costs", ""] + mrow(r["x2_m"]),
                ["0 costs (diagnostic only)", ""] + mrow(r["gross_m"]),
                ["Rules as specified (BTC OOS)", ""] + mrow(r["spec_m"]),
                ["**Holdout** (BTC, frozen rules)", "2025-10→2026-09"] + mrow(h["metrics"])]
        L.append(table(["Run", "Period"] + [c[0] for c in MCOLS], rows))
        L.append("")
        L.append(f"- Random-entry baseline: setup expectancy is at the **{r['rand_pct']:.0f}th percentile** of 1,000 runs "
                 f"(median random {f(float(np.median(r['rand_exp'])) if len(r['rand_exp']) else np.nan, 'r')}).")
        L.append(f"- Deflated Sharpe: **{f(r['dsr'])}** · IS→OOS degradation ratio (OOS ÷ mean train expectancy): "
                 f"{f(r['degradation'])}")
        L.append(f"- BTC buy & hold over the same OOS span: {r['bh']['return']:+.0%} ({r['bh']['cagr']:+.0%} a year).")
        picks = [str(c) if c else "–" for c in r["final"].choices]
        L.append(f"- Chosen per test quarter: {', '.join(f'`{p}`' for p in picks)}")
        L.append(f"- Holdout choices: {', '.join(f'`{c}`' if c else '`–`' for c in h['choices'])}")
        L.append("\n**Pass checks**\n")
        L.append(table(["Rule", "Result", "Value"], [[c[0], "✅" if c[1] else "❌", c[2]] for c in r["checks"]] +
                       [["holdout expectancy > 0", "✅" if h["metrics"]["trades"] and h["metrics"]["expectancy"] > 0
                         else "❌", f"{f(h['metrics']['expectancy'], 'r')} ({h['metrics']['trades']} trades)"]]))
        L.append(f"\nVerdict: **{verdict_md(h['label'])}**\n")

    L.append("## Look-ahead tests and the holdout protocol\n")
    L += [f"- {x}" for x in notes["lookahead"]]
    L.append(f"- Frozen choices: `reports/lab3_frozen.json` (sha256 `{frozen['sha256'][:16]}…`), committed before the "
             f"holdout was loaded. The holdout script refuses to run twice.")
    L.append("")
    L.append("## Data gaps and assumptions\n")
    L += [f"- {x}" for x in notes["assumptions"]]
    L.append("")
    L.append("## Candidates for paper trading\n")
    L.append(notes["candidates"] + "\n")
    return "\n".join(L) + "\n"


def verdict_md(v: str) -> str:
    return {"PASS": "✅ PASS", "FAIL": "❌ FAIL", "INCONCLUSIVE": "⚠️ INCONCLUSIVE", "DEV-PASS": "✅ dev-pass"}.get(v, v)
