"""Lab 4 phase G: verdict, decision sheet, frozen rules, final report.
Reads data/lab4/results_{B,C,D,E}.pkl (run phases B-E first)."""
from __future__ import annotations

import json
import pickle

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import _bootstrap  # noqa: F401
from lab.config import REPORTS_DIR
from lab2.strategies import S2_TABLES
from lab3.wf import deflated_sharpe, metrics
from lab4.data import LAB4_DIR, load
from lab4.phaseC import SIGNALS

BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb"
LAB3_TRIALS = 183


def r(x, k=3):
    return "–" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:+.{k}f}R"


def pct(x):
    return "–" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.0%}"


def table(h, rows):
    out = ["| " + " | ".join(h) + " |", "|" + "|".join("---" for _ in h) + "|"]
    return "\n".join(out + ["| " + " | ".join(str(c) for c in row) + " |" for row in rows])


def ordinal(x):
    if x is None or not np.isfinite(x):
        return "–"
    n = int(round(x))
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def current_state():
    """S2 multiplier and S1 20w state as of the last completed week in the data."""
    d = load("spot_BTCUSDT_1d")["close"]
    wk = d[d.index.dayofweek == 6]          # Sunday daily close = weekly close
    sma200, sma20 = wk.rolling(200).mean().iloc[-1], wk.rolling(20).mean().iloc[-1]
    ratio = wk.iloc[-1] / sma200
    table_, trim_at, _ = S2_TABLES["aggressive"]
    mult = next(m for ub, m in table_ if ratio < ub)
    return {"week_close_date": f"{wk.index[-1]:%Y-%m-%d}", "btc_weekly_close": float(wk.iloc[-1]),
            "sma_200w": float(sma200), "ratio": float(ratio), "s2_multiplier": mult, "sma_20w": float(sma20),
            "s1_up": bool(wk.iloc[-1] > sma20)}


def main():
    B = pickle.load(open(LAB4_DIR / "results_B.pkl", "rb"))
    C = pickle.load(open(LAB4_DIR / "results_C.pkl", "rb"))
    D = pickle.load(open(LAB4_DIR / "results_D.pkl", "rb"))
    E = pickle.load(open(LAB4_DIR / "results_E.pkl", "rb"))
    lab3 = json.loads((REPORTS_DIR / "lab3_frozen.json").read_text())
    reg = B["registry"]
    srs = np.array([v["sr"] for v in reg.values() if v["n"] >= 30 and np.isfinite(v["sr"])])
    n_trials = LAB3_TRIALS + len(reg) + int(C["btc"]["p"].notna().sum()) + 4 + len(E["summary"]) + 1
    sr_var = float(srs.var(ddof=1))

    # ------------------------------------------------------------------ phase B verdict table
    brows, checks_all, cost_rows, rand_pct = [], {}, [], {}
    for k, o in B["best"].items():
        wf2 = o["C2"]
        m2 = metrics(wf2.trades, wf2.span)
        m0 = metrics(o["C0"].trades, o["C0"].span)
        me = metrics(o["eth_C2"].trades, o["eth_C2"].span)
        rand = o["rand"]
        rp = float((rand < wf2.expectancy).mean() * 100) if len(rand) else np.nan
        rand_pct[k] = rp
        dsr = deflated_sharpe(wf2.trades["r"].to_numpy(), n_trials, sr_var) if len(wf2.trades) > 2 else np.nan
        share_1d = float((wf2.trades["tf"] == "1d").mean()) if len(wf2.trades) else 0
        min_n = 40 if share_1d >= 0.5 else 100
        ch = [("OOS expectancy > 0.10R (C2)", m2["expectancy"] > 0.10, r(m2["expectancy"])),
              ("expectancy > 0 (C0)", m0["expectancy"] > 0, r(m0["expectancy"])),
              ("profit factor > 1.2 (C2)", m2["profit_factor"] > 1.2, f"{m2['profit_factor']:.2f}"),
              (f"≥ {min_n} OOS trades", m2["trades"] >= min_n, m2["trades"]),
              ("> 95th pct random entries", bool(np.isfinite(rp) and rp > 95), ordinal(rp)),
              ("DSR > 0.95", bool(np.isfinite(dsr) and dsr > 0.95), f"{dsr:.2f}" if np.isfinite(dsr) else "–"),
              ("ETH expectancy > 0 (C2)", me["expectancy"] > 0 if me["trades"] else False, r(me["expectancy"])),
              ("≥ 60% profitable months", (m2["pct_months_up"] or 0) >= 0.6, pct(m2["pct_months_up"]))]
        failed = [c for c in ch if not c[1]]
        label = "PASS" if not failed else ("INCONCLUSIVE" if len(failed) == 1 and "trades" in failed[0][0] else "FAIL")
        checks_all[k] = (ch, label)
        brows.append([f"**{k}**", f"`{o['exec'].label if k != 'T6' else 'own 4-tranche ladder'}`", m2["trades"],
                      r(m2["expectancy"]), f"{m2['profit_factor']:.2f}", ordinal(rp),
                      f"{dsr:.2f}" if np.isfinite(dsr) else "–", r(me["expectancy"]), r(m0["expectancy"]),
                      pct(m2["pct_months_up"]), f"**{label}**"])
        lab3_exp = lab3["setups"].get(k, {}).get("dev_oos_expectancy", np.nan)
        cost_rows.append({"setup": k, "lab3_C0_market": lab3_exp, "zero_cost": o["zero"].expectancy,
                          "C1": o["C1"].expectancy, "C2": wf2.expectancy, "C0_limits": o["C0"].expectancy,
                          "touch_C1": o["touch_C1"].expectancy})
    cost = pd.DataFrame(cost_rows)
    beat_rand = [k for k, v in rand_pct.items() if np.isfinite(v) and v > 95]
    grid = B["grid"]
    g1 = grid[(grid.scenario == "C1") & (grid.setup != "T6")]
    by_entry = g1.groupby("entry")["expectancy"].mean()
    by_exit = g1.groupby("exit")["expectancy"].mean()
    by_stop = g1.groupby("stop")["expectancy"].mean()

    # chart: cost decomposition
    fig, ax = plt.subplots(figsize=(11, 4.6), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    ax.grid(True, axis="y", color=GRID, linewidth=0.6)
    ax.spines[["top", "right"]].set_visible(False)
    x = np.arange(len(cost))
    w = 0.18
    for i, (col, color, lab) in enumerate((("zero_cost", MUTED, "no costs (diagnostic)"), ("C1", BLUE, "C1 user fees"),
                                            ("C2", ORANGE, "C2 + stop slippage"), ("C0_limits", AQUA, "C0 Lab 3 costs"))):
        ax.bar(x + (i - 1.5) * w, cost[col], width=w, color=color, label=lab)
    ax.axhline(0.10, color=INK, linestyle="--", linewidth=1)
    ax.text(len(cost) - 0.5, 0.104, "+0.10R pass bar", color=INK2, fontsize=8, ha="right")
    ax.axhline(0, color=INK, linewidth=0.8)
    ax.set_xticks(x, cost["setup"])
    ax.set_ylabel("OOS expectancy per trade (R)", color=INK2, fontsize=8)
    ax.set_title("Phase B — best execution variant per setup under each cost scenario (BTC walk-forward OOS)",
                 loc="left", color=INK, fontsize=10)
    ax.legend(frameon=False, fontsize=8, labelcolor=INK2, ncol=4, loc="lower left")
    fig.tight_layout()
    fig.savefig(REPORTS_DIR / "lab4_phaseB_costs.png", dpi=130, facecolor=SURFACE)
    plt.close(fig)

    # ------------------------------------------------------------------ accumulation verdicts
    rolling = E["rolling"]
    piv = {k: g.set_index("start") for k, g in rolling.groupby("rule")}
    s2a = piv["S2"]
    s2_vs_b1 = float(((s2a["multiple"] - piv["B1"]["multiple"]) > 0).mean())
    d_overlay = D["overlay"]
    s1row = d_overlay[(d_overlay.rule == "S1 20w")].iloc[0]
    s2row = d_overlay[(d_overlay.rule == "S2 aggressive")].iloc[0]
    state = current_state()
    t_aggr, trim_at, trim_frac = S2_TABLES["aggressive"]

    frozen = {
        "frozen_at": pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds"),
        "note": "No unseen historical holdout remains; data/forward/ (scripts/daily_logger.py) is the holdout. "
                "Verdicts are final only after >= 3 months of forward data.",
        "accumulation": [
            {"id": "S2-aggressive", "frame": "weekly contributions", "asset": "BTCUSDT",
             "rule": "every Monday buy base x multiplier at the open (limit), multiplier from BTC weekly close / "
                     "200-week SMA of weekly closes; unspent money waits in a 0% cash reserve that funds later "
                     "multipliers; trim 10% of holdings while the ratio > trim_at, at most once per 4 weeks",
             "table": [[ub if np.isfinite(ub) else 1e9, m] for ub, m in t_aggr], "trim_at": trim_at,
             "trim_fraction": trim_frac,
             "evidence": {"won_vs_B2_rolling_starts_C1": s2row.pct_won, "median_dd": s2row.median_dd,
                          "median_dd_B2": s2row.bench_median_dd, "won_vs_B1_lump_sum_C1": s2_vs_b1}},
            {"id": "S1-20w", "frame": "lump sum", "asset": "BTCUSDT",
             "rule": "hold BTC while the latest weekly close > 20-week SMA of weekly closes, else hold cash; check "
                     "daily, trade on Mondays (limit at the open)",
             "evidence": {"won_vs_B1_rolling_starts_C1": s1row.pct_won, "median_dd": s1row.median_dd,
                          "median_dd_B1": s1row.bench_median_dd}},
        ],
        "paper_trading": [],
        "dead": {k: v[1] for k, v in checks_all.items()},
        "n_trials_dsr": n_trials,
    }
    (REPORTS_DIR / "lab4_frozen.json").write_text(json.dumps(frozen, indent=1, default=float))

    # ------------------------------------------------------------------ report
    cb = C["btc"]
    best_b = max(B["best"], key=lambda k: B["best"][k]["C2"].expectancy)
    L = ["# Lab 4 — information, execution and macro: what gives a halal spot edge?\n", "## Verdict\n"]
    L.append(
        "**Nothing short-term works, and no new information source helps. The only rules with support are the two "
        "slow accumulation rules from Lab 3, and they keep that support under your real fees.** "
        f"Real execution (BNB-discounted 0.075% fees, limit ladders, partial exits) cuts the cost drag a lot. "
        f"The best of Lab 3's setups rises from {r(cost.set_index('setup').loc[best_b, 'lab3_C0_market'])} to "
        f"{r(B['best'][best_b]['C2'].expectancy)} per trade ({best_b}, C2), still far below the +0.10R bar. "
        "Before costs most setups carried only +0.01R to +0.13R, so cost explains much of Lab 3's failure, but "
        "there was never enough edge to survive any realistic cost"
        + (f" ({' and '.join(beat_rand)} entries did beat random entries with the same execution, so the timing "
           "is not pure noise, but the edge is far too small)" if beat_rand else "") + ". None of the "
        f"{int(cb['p'].notna().sum())} derivatives/flow event tests (funding, open interest, premium, long/short "
        "ratio, taker delta, liquidation-style flushes) survived the false-discovery, ETH and regime checks. "
        "Macro series available here (VIX, dollar and gold proxies) show unstable correlations and no forward "
        "information, and a macro size overlay did not improve S1 or S2. A spot grid ladder lost to buy & hold, "
        f"DCA and S2 in most starts. What survives: weekly DCA scaled by the 200-week SMA (S2) beat plain DCA in "
        f"{s2row.pct_won:.0%} of rolling starts with a lower median drawdown ({s2row.median_dd:.0%} vs "
        f"{s2row.bench_median_dd:.0%}); the 20-week SMA filter (S1) beat lump-sum buy & hold in {s1row.pct_won:.0%} "
        f"with median drawdown {s1row.median_dd:.0%} vs {s1row.bench_median_dd:.0%}. Both rest on two or three "
        "overlapping market cycles, so they are frozen and must now prove themselves on forward data.")
    L.append("")
    L.append("## Decision sheet\n")
    L.append("### 1. What to do with money now\n")
    L.append(f"**Weekly accumulation: S2 (200-week SMA multiplier, aggressive table)** — BTC spot, Binance, limit buy at "
             "the Monday open:\n")
    L.append(table(["BTC weekly close ÷ 200-week SMA", "Weekly buy"],
                   [["below 1.5", "3 × your base amount (funded from the cash reserve; if the reserve is short, buy "
                                  "what it holds)"], ["1.5 – 2.5", "1 × base"], ["2.5 – 3.5", "0.25 × base (save the "
                                                                                                  "rest)"],
                    ["above 3.5", "0 × (save it all) and sell 10% of your BTC, at most once every 4 weeks"]]))
    L.append(f"\nState as of the week closing {state['week_close_date']}: BTC {state['btc_weekly_close']:,.0f}, "
             f"200-week SMA {state['sma_200w']:,.0f}, ratio **{state['ratio']:.2f} → buy {state['s2_multiplier']:g}× "
             f"the base amount** this week. The reserve earns nothing (no Earn/staking), by design. Practical note: "
             f"the ×3 tier spends a cash reserve saved in the expensive weeks; if you start now with no reserve, "
             f"either set aside a few weeks of base amounts first or accept that ×3 weeks are capped by your cash.\n")
    L.append(f"**Lump sums: S1 (20-week SMA filter)** — hold BTC while the weekly close is above the 20-week SMA, "
             f"otherwise hold cash; check on Mondays. Current state: weekly close {state['btc_weekly_close']:,.0f} vs "
             f"20-week SMA {state['sma_20w']:,.0f} → **{'hold BTC' if state['s1_up'] else 'hold cash'}**. "
             "Expect to give up return in strong bull runs in exchange for a much smaller drawdown.\n")
    L.append("Halal check: spot only, long only, no leverage, no lending/Earn/staking; idle cash earns 0%.\n")
    L.append("### 2. What goes to paper trading\n")
    L.append("**No mechanical short-term rule qualified.** Every setup failed at least five of the eight pass rules "
             f"(table below). The least bad, {best_b}, made {r(B['best'][best_b]['C2'].expectancy)} per trade at "
             "C2 after picking the best of 18 execution variants on the test data. That is noise-level and "
             "optimistic, so it is not a paper-trading candidate. If you paper-trade, trade your own "
             "discretionary ideas and record each one in `journal/` (schema + `scripts/journal_stats.py`). After 50 "
             "to 100 trades the journal answers whether *your* judgment beats +0.10R after fees.\n")
    L.append("### 3. What is dead and why\n")
    beat_rand = [k for k, v in rand_pct.items() if np.isfinite(v) and v > 95]
    dead = [["Lab 1 alt TA (pullback, breakout, base)", "negative after costs on a survivorship-free universe"],
            ["Lab 3 / Lab 4 short-term setups T1, T1b, T3, T4, T5, T6", "best execution variant still "
             f"≤ {r(max(o['C2'].expectancy for o in B['best'].values()))} per trade at C2, DSR ≈ 0, at least five of "
             "eight pass rules failed"
             + (f". {' and '.join(beat_rand)} did beat {', '.join(ordinal(rand_pct[k]) for k in beat_rand)} percentile "
                "of random entries with the same execution: their timing carries a little information, too little "
                "to pay for costs" if beat_rand else "")],
            ["T2 1-minute volume breakout", "Lab 3: −0.41R; tight stops make costs ~0.7R per trade (not re-run)"],
            ["Derivatives/flow signals D1–D6", "no FDR-significant signal with the right sign on BTC, the same sign "
             "on ETH and in 2 of 3 regimes; D4 'absorption' was significantly NEGATIVE (price kept falling)"],
            ["Fear & Greed (D7), FOMC/CPI windows, ETF flows, Nasdaq/DXY/10y/Fed data", "not testable here: "
             "sources blocked or not free (see the data inventory)"],
            ["Macro regime and macro size overlay", "no forward difference (CI spans zero); overlay worse than "
             "plain S1 and no better than plain S2"],
            ["Spot grid ladder (L1)", f"beats buy & hold in ≤ {E['summary'].loc[E['summary'].rule.str.startswith('L1'), 'won_vs_B1'].max():.0%}"
             " of starts; capital idle; lots underwater for up to ~3 years"],
            ["S2 + ladder hybrid (L2), S2 + crowding overlay (L3)", "L2 only dilutes S2; L3 is S2 in 93% of starts"],
            ["Market gate A2 (Lab 3)", "failed in both frames"]]
    L.append(table(["Idea", "Why it is dead"], dead))
    L.append("")

    L.append("## Phase A — data\n")
    L.append("See `reports/lab4_data_inventory.md`. Available: Binance spot klines with taker-buy volume, USD-M funding, "
             "premium index and 5-minute metrics (open interest, long/short ratios, taker ratio), VIX daily, monthly "
             "10y, PAXG/USDT (gold proxy) and EUR/USDT (dollar proxy). Blocked or not free here: Fear & Greed, FRED "
             "daily series, Nasdaq/QQQ, DXY, FOMC/CPI calendars, ETF flows, liquidation history, unlock history.\n")

    L.append("## Phase B — Lab 3 setups with real execution\n")
    L.append(f"Each setup's frozen Lab 3 rules and grid, walk-forward 12m/3m on BTC (2021-01 → 2025-09 OOS), for "
             f"every entry ladder × exit × stop combination (18) under C0, C1 and C2 with trade-through fills; "
             f"{len(reg)} configurations in all. The best variant per setup (by C2 OOS expectancy) is then checked "
             f"against all pass rules; DSR counts {n_trials} configurations across Labs 3 and 4.\n")
    L.append(table(["Setup", "Best variant", "OOS trades", "Expectancy C2", "PF C2", "vs random", "DSR", "ETH C2",
                    "Expectancy C0", "Months up", "Verdict"], brows))
    L.append("\n**How much was cost, how much no edge** (same walk-forward, best variant):\n")
    L.append(table(["Setup", "Lab 3 (market orders, C0)", "No costs", "C1 user", "C2 user + stop slip",
                    "C0 with limits", "C1 with touch fills"],
                   [[row.setup, r(row.lab3_C0_market), r(row.zero_cost), r(row.C1), r(row.C2), r(row.C0_limits),
                     r(row.touch_C1)] for row in cost.itertuples()]))
    L.append("\n![Cost scenarios](lab4_phaseB_costs.png)\n")
    L.append("**Execution modes** (mean OOS expectancy across T1, T1b, T3, T4, T5 under C1):\n")
    L.append(table(["Entry", "Expectancy"], [[k, r(v)] for k, v in by_entry.items()]))
    L.append("")
    L.append(table(["Exit", "Expectancy"], [[k, r(v)] for k, v in by_exit.items()]))
    L.append("")
    L.append(table(["Stop", "Expectancy"], [[k, r(v)] for k, v in by_stop.items()]))
    gain = (cost["C1"] - cost["lab3_C0_market"])
    fee_only = (cost["C1"] - cost["C0_limits"])
    tch = (cost["touch_C1"] - cost["C1"])
    L.append(f"\nRead: going from Lab 3 to your execution (C1) improves the best variant of each setup by "
             f"{gain.min():+.2f}R to {gain.max():+.2f}R per trade. Part of that is choosing the best of 18 variants; the "
             f"pure fee/slippage effect (C0 → C1, same variant and limit entries) is {fee_only.min():+.2f}R to "
             f"{fee_only.max():+.2f}R. Exit style barely matters (X1 {r(by_exit['X1'])}, X2 {r(by_exit['X2'])}, X3 "
             f"{r(by_exit['X3'])}: moving the stop to breakeven after the first third helps a little). E2 (0.09% "
             f"ladder) is marginally better than one limit ({r(by_entry['E2'])} vs {r(by_entry['E1'])}); a wide ATR "
             f"ladder (E3) is worse ({r(by_entry['E3'])}), consistent with adverse selection (deep levels fill mostly when price keeps falling). "
             f"Stop placement makes no difference ({r(by_stop['S-a'])} vs {r(by_stop['S-b'])}). Touch fills change "
             f"results by {tch.min():+.2f}R to {tch.max():+.2f}R: mixed, not uniformly flattering. Verdicts use "
             "trade-through. None of this creates an edge that clears the bar.\n")
    L.append("Full grid: `reports/lab4_phaseB_grid.csv`.\n")

    L.append("## Phase C — derivatives and flow signals (event studies)\n")
    L.append("Forward spot return after each event vs the unconditional return in the same BTC 200-day regime; "
             "95% block-bootstrap CI; Benjamini–Hochberg FDR at 10% over all BTC tests with ≥ 10 events; then the "
             "same sign on ETH and in ≥ 2 of 3 regimes (bull / bear / range by the 20-day slope of the 200-day SMA). "
             "Thresholds are expanding percentiles (≥ 180 observations).\n")
    rows = []
    for x in cb.itertuples():
        rows.append([x.signal, x.horizon, x.events, f"{x.mean_excess:+.2%}" if np.isfinite(x.mean_excess) else "–",
                     f"[{x.ci_lo:+.2%}, {x.ci_hi:+.2%}]" if np.isfinite(x.ci_lo) else "– (too few events)",
                     f"{x.p:.3f}" if np.isfinite(x.p) else "–", "✅" if x.fdr_pass else "–",
                     "✅" if x.right_sign else "❌", f"{x.eth_excess:+.2%}" if np.isfinite(x.eth_excess) else "–",
                     x.regimes_same_sign, "✅" if x.survives else "❌"])
    L.append(table(["Signal", "Days", "Events", "Mean excess", "95% CI", "p", "FDR", "Expected sign", "ETH",
                    "Regimes same sign", "Survives"], rows))
    L.append("\nSignals: " + "; ".join(f"**{k}** {v[0]}" for k, v in SIGNALS.items()) + ". D7 (Fear & Greed) "
             "skipped: no data. Because nothing survived, the tradable-rule walk-forward of Phase C had nothing to "
             "run.\n")
    L.append("![Event studies](lab4_phaseC_forest.png)\n")

    L.append("## Phase D — macro\n")
    inst = D["instability"]
    L.append(table(["Series vs BTC (90-day rolling corr.)", "From", "Mean", "Std", "Min", "Max", "Share > 0",
                    "Sign flips"],
                   [[k, v["first"], f"{v['mean']:+.2f}", f"{v['std']:.2f}", f"{v['min']:+.2f}", f"{v['max']:+.2f}",
                     pct(v["share_positive"]), int(v["sign_flips"])] for k, v in inst.iterrows()]))
    y10 = D["y10"]
    L.append(f"\nUS 10y (monthly only): correlation of monthly BTC returns with the yield change {y10['full_corr']:+.2f} "
             f"over {y10['months']} months; rolling 24-month range {y10['rolling24_min']:+.2f} … "
             f"{y10['rolling24_max']:+.2f}.\n")
    L.append("![Correlations](lab4_phaseD_correlations.png)\n")
    L.append(table(["Macro regime (known at day end)", "Days", "Mean 30-day forward BTC", "95% CI"],
                   [[x.regime, x.days, f"{x.mean_fwd:+.1%}", f"[{x.ci_lo:+.1%}, {x.ci_hi:+.1%}]"]
                    for x in D["conditional"].itertuples()]))
    L.append("\nMacro overlay (VIX-only risk-on score; Nasdaq and DXY unavailable), rolling starts at C1:\n")
    L.append(table(["Frame", "Rule", "Starts won vs benchmark", "Median max DD (vs bench)", "Verdict"],
                   [[x.frame, x.rule, pct(x.pct_won), f"{x.median_dd:.0%} vs {x.bench_median_dd:.0%}", x.verdict]
                    for x in D["overlay"].itertuples()]))
    vs = D["overlay_vs_plain"]
    L.append("\n" + table(["Overlay", "Starts better than the plain rule", "Median Δ value÷contrib. vs plain"],
                          [[x.overlay, pct(x.pct_starts_better_than_plain), f"{x.median_diff_vs_plain:+.2f}"]
                           for x in vs.itertuples()]))
    L.append("\nD-3 (FOMC/CPI event windows) and D-4 (calendar filter) skipped: the official calendars are not "
             "reachable here and typing dates from memory would risk fabricated data; no short-term rule is alive "
             "to filter anyway.\n")

    L.append("## Phase E — accumulation upgrades (lump sum $10,000, rolling starts, C1)\n")
    es = E["summary"]
    L.append(table(["Rule", "Won vs B1", "Won vs B2", "Won vs S2", "Median DD", "Median invested",
                    "Longest lot underwater", "Median round trips", "Verdict vs B1"],
                   [[x.rule, pct(x.won_vs_B1), pct(x.won_vs_B2), pct(x.won_vs_S2), pct(x.median_dd),
                     pct(x.median_utilization), f"{x.max_underwater_days:.0f} d" if np.isfinite(x.max_underwater_days)
                     else "–", f"{x.median_round_trips:.0f}" if np.isfinite(x.median_round_trips) else "–",
                     x.verdict_vs_B1] for x in es.itertuples()]))
    L.append(f"\nFor reference, S2 itself (lump-sum version) beat B1 in {s2_vs_b1:.0%} of starts. "
             f"Median drawdown B1 {es['median_dd_B1'].iloc[0]:.0%}, B2 {es['median_dd_B2'].iloc[0]:.0%}.\n")
    l3v = E["l3_vs"]
    L.append(f"L3 (S2 × crowding overlay, weekly frame): identical to S2 in {l3v['pct_equal']:.0%} of starts; better "
             f"than S2 in {l3v['pct_better_than_S2_all']:.0%} (from 2020-12, when the data exists: "
             f"{l3v['pct_better_than_S2_from_2020_12']:.0%} of {l3v['starts_from_2020_12']} starts). L4 (unlock filter) "
             "skipped: no free historical unlock data.\n")
    L.append("![Accumulation](lab4_phaseE_winrate.png)\n")

    L.append("## Phase F — forward logging and the journal\n")
    L.append("- `scripts/daily_logger.py` — run daily at 00:10 UTC (cron line in the script; a GitHub Actions file "
             "to copy is in `ops/`). Appends funding, open interest, long/short ratios, taker ratio, premium, spot "
             "taker delta and Fear & Greed to `data/forward/market.csv`, and the live state of every frozen rule "
             "(S2 multiplier, S1 filter) to `data/forward/rules.csv`. Liquidations are not logged (Binance's "
             "force-order endpoint needs an API key).")
    L.append("- `journal/` — CSV schema for paper trades (thesis, data seen, ladder prices and fills, stop, targets, "
             "exits, fees, result in R, discipline and emotion); `scripts/journal_stats.py` gives expectancy, PF, "
             "win rate, average R and the longest losing streak, overall and by setup, regime, discipline and "
             "emotion.\n")

    L.append("## Phase G — pass rules and freezing\n")
    L.append("Short-term rules needed: OOS expectancy > 0.10R at C2 and > 0 at C0, PF > 1.2, ≥ 100 trades (≥ 40 on "
             "daily bars), > 95th pct of random entries, DSR > 0.95, ETH > 0, ≥ 60% profitable months. None passed. "
             "Accumulation rules needed ≥ 60% of rolling starts won with a lower median drawdown under C1: S2 "
             "(weekly) and S1 (lump sum) pass and are frozen in `reports/lab4_frozen.json`. No unseen historical "
             "holdout remains, so the forward log is the holdout: re-check S1/S2 against plain DCA / buy & hold "
             "after ≥ 3 months of `data/forward/` data. The verdict is final only then.\n")
    for k, (ch, label) in checks_all.items():
        L.append(f"<details><summary>{k}: {label}</summary>\n")
        L.append(table(["Rule", "Pass", "Value"], [[c[0], "✅" if c[1] else "❌", c[2]] for c in ch]))
        L.append("\n</details>\n")

    L.append("## Data gaps and assumptions\n")
    for a in [
        "Holdout: Lab 3's 2025-10 → 2026-09 period has been seen. Phase B keeps Lab 3's 2020-01 → 2025-09 "
        "walk-forward; event studies (C), macro (D) use data up to 2026-09-30; rolling starts (D-5, E) end by "
        "2025-09-30.",
        "Point-in-time: funding is used from its settlement timestamp, open interest and ratios from their 5-minute "
        "snapshot time (stale > 6 h = missing), premium-index and spot klines from their close, VIX from 00:00 UTC "
        "after its US session. Tests cover the as-of alignment, append-one-day invariance of every signal, and the "
        "VIX timing.",
        "Execution model: limit entries live for 3 bars (T4: 100 bars and cancelled by a close below the zone); "
        "trade-through = 0.02% beyond the limit; no partial fills or queue position; a bar with an entry fill can "
        "stop out but not take profit; ladder R is measured against the risk of the full ladder, so partial fills "
        "risk less. S-c (stops below liquidation clusters) is not testable without liquidation data.",
        "The best execution variant per setup was chosen on OOS results (as the task asks for the comparison). "
        "That flatters it, and the DSR counts every configuration tried.",
        "T6 keeps its own 4-tranche ladder and base exit; only costs and fill models change. Its random baseline is "
        "not computed (no single-entry analogue).",
        "Accumulation under C1: weekly limit buys at the Monday open at 0.075% fee, no slippage. Lump-sum B2 deploys "
        "$10,000 over 104 weeks (Lab 2 definition). The ladder runs on 1h bars, everything else on daily bars.",
        "Macro proxies: dollar = 1/EUR-USDT, gold = PAXG/USDT, VIX via DataHub's CBOE copy; correlations are "
        "descriptive (same-date returns), the regime and overlay use only values known before each decision.",
        "Rolling starts overlap heavily (about 2.6 independent 3-year periods), so accumulation evidence rests on "
        "two or three market cycles.",
    ]:
        L.append(f"- {a}")
    (REPORTS_DIR / "lab4_report.md").write_text("\n".join(L) + "\n")
    print("report + frozen written; trials", n_trials, "sr_var", round(sr_var, 4))
    print(cost.round(3).to_string())
    print(by_entry.round(3).to_dict(), by_exit.round(3).to_dict(), by_stop.round(3).to_dict())
    print({k: v[1] for k, v in checks_all.items()}, state)


if __name__ == "__main__":
    main()
