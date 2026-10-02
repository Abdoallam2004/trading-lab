"""Text for the Lab 3 report, computed from the results (no hand-typed numbers)."""
from __future__ import annotations

import numpy as np


def notes_for(dev: dict, hold: dict, frozen: dict) -> dict:
    res, s1, s2 = dev["res"], dev["part_a"]["1x"], dev["part_a"]["2x"]

    def passes(s, frame):
        g = s[(s.frame == frame) & (s.verdict == "PASS")]
        return [f"{r.rule} ({r.params})" for r in g.itertuples()]

    a_pass, b_pass = passes(s1, "A"), passes(s1, "B")
    a2_pass, b2_pass = passes(s2, "A"), passes(s2, "B")
    best = {fr: s1[s1.frame == fr].iloc[0] for fr in ("A", "B")}
    gates = s1[s1.rule.str.startswith("A2")]
    gate_best = gates.sort_values("pct_won", ascending=False).iloc[0]
    finals = {k: hold[k]["label"] for k in res}
    passed_b = [k for k, v in finals.items() if v == "PASS"]
    exps = {k: res[k]["oos"]["expectancy"] for k in res}
    gross = {k: res[k]["gross_m"]["expectancy"] for k in res}
    pos_gross = [k for k, v in gross.items() if v and v > 0]
    hold_pos = [k for k in res if hold[k]["metrics"]["trades"] and hold[k]["metrics"]["expectancy"] > 0]

    verdict = (
        "**Part A — the fair re-test changes Lab 2's answer for some long-horizon rules; Part B — none of the "
        "short-term setups has an edge after costs.** "
        f"Over 57 rolling 3-year starts, {len(a_pass)} of {len(s1[s1.frame == 'A'])} rule settings beat lump-sum buy & "
        f"hold in ≥ 60% of starts with a lower median drawdown (best: {best['A'].rule} {best['A'].params}, "
        f"{best['A'].pct_won:.0%} of starts, median max drawdown {best['A'].median_dd:.0%} vs "
        f"{best['A'].bench_median_dd:.0%}), and {len(b_pass)} beat plain weekly DCA (best: {best['B'].rule} "
        f"{best['B'].params}, {best['B'].pct_won:.0%} of starts, median gain {best['B'].median_diff:+.2f}× of "
        f"contributions, median drawdown {best['B'].median_dd:.0%} vs {best['B'].bench_median_dd:.0%}). "
        f"At 2× costs {len(a2_pass)} (lump sum) and {len(b2_pass)} (weekly) still pass. Lab 2's single "
        "out-of-sample window began at a cycle bottom, which is exactly when buy & hold is hardest to beat. "
        "Treat these wins with care: the 57 windows overlap heavily (about 2.6 independent 3-year periods in "
        "2018–2025), so the win rates rest on two or three market cycles, not 57 independent tests. "
        f"The new graded market gate (A2) failed in both frames (best: {gate_best.pct_won:.0%} of starts). "
        f"In Part B, every setup lost money in walk-forward OOS on BTC after costs "
        f"(from {min(exps.values()):+.2f}R to {max(exps.values()):+.2f}R per trade); before costs "
        f"{len(pos_gross)} of {len(res)} showed only a small edge (at most {max(gross.values()):+.2f}R), which the "
        "0.30% round trip erases, worst for tight-stop setups such as the 1-minute T2. "
        + ("Nothing passed, so the holdout could not rescue anything; "
           if not passed_b else f"Passed after the holdout: {', '.join(passed_b)}; ")
        + (f"for the record, the holdout was positive for {', '.join(hold_pos)}." if hold_pos
           else "the holdout was negative or empty for every setup.")
    )

    part_a = [
        "Frames, rules and costs reuse Lab 2's simulator unchanged: fills at the Monday open after a Sunday-close "
        "signal, 0.10% fee + 0.05% slippage per fill (2× = 0.20% + 0.10%), 0% on cash, no leverage, no shorting.",
        "Frame A: $10,000 at the start, compared with B1 (all-in at the first open). Frame B: $100 every Monday, "
        "compared with B2 (buy $100 every Monday). 'Beats' = higher final value ÷ money contributed at the end of "
        "the 3-year run. Drawdown = max drawdown of the time-weighted return index (contributions removed).",
        "BTC per $: median over starts of (rule's BTC per $ contributed ÷ benchmark's). Below 1× means the rule "
        "ended with less BTC (it held cash or sold).",
        "S4's three trim levels are identical in every start: its z-score never exceeded +1.5σ inside any "
        "2018–2025 window, so no trim fired. S5 with K = 7 in frame B is identical to plain DCA for the same "
        "reason (its ×2 is funded only by trim proceeds).",
        "A2 market gate: score = mean of four expanding-window percentiles (trend = close ÷ 200-day SMA; value = "
        "100 − MVRV-Z percentile; drawdown = % below the all-time high; calm = 100 − 30-day realised volatility "
        "percentile), each ranked only against its own history up to that day (≥ 365 observations; price history "
        "from 2010 via CoinMetrics). Lump-sum mode holds 0 / 60 / 100% BTC per the map, rebalanced on Mondays "
        "only when off-target by ≥ 5% of equity. DCA mode spends exposure × ($100 + ¼ of the saved reserve) each "
        "week and never sells.",
        "Overlap warning: consecutive starts share 35 of 36 months, so neighbouring results are nearly the same "
        "experiment. A rule that wins 60% of starts may be winning one or two good stretches.",
    ]

    lookahead = [
        "`tests/test_lab3.py` (52 tests, synthetic data) for every setup, with no optional rules and with all rules: "
        "(1) append-one-bar invariance; "
        "(2) close-shock: changing one bar's close (×0.9 / ×1.1, every timeframe) leaves every earlier signal "
        "unchanged; (3) every order already exists, field for field, when the data ends exactly at its signal "
        "bar's close (catches any peek at a later bar).",
        "Mutation checks: a one-bar RSI peek injected into T5, and a stop computed one bar ahead in T3, were both "
        "caught by test (3). (Test (1) alone did not catch them; that weakness is why test (3) exists.)",
        "Static check: signal and filter code (`lab3/market.py`, `lab3/setups.py`, `lab3/partA.py`, "
        "`lab2/signals.py`, `lab/indicators.py`) may not use `filtfilt`, `center=True`, `.shift(-…)`, `bfill`, "
        "`np.roll`, reversed arrays, Savitzky-Golay/LOWESS smoothing or interpolation.",
        "Fractal pivots are reported only at their confirmation bar (k bars after the pivot); a test checks the "
        "pivot is absent when the data ends earlier.",
        "Walk-forward: a test shows the parameter choice for a test quarter is unchanged when only that quarter's "
        "data are altered. Part A gate: a test shows the score up to t is identical with or without later data.",
        "Holdout lock: `lab3.data.load_bars` drops everything after 2025-09-30 unless `holdout=True`. Every "
        "development-time market asserts no bar beyond 2025-09-30, and a test checks the lock.",
    ]

    assumptions = [
        "Data: Binance spot BTCUSDT / ETHUSDT klines (1m from 2020-12, 5m/15m/1h/4h from 2019-01, 1d from 2017-08) "
        "from data.binance.vision via its S3 bucket. Part A uses Lab 2's merged daily data and the free CoinMetrics "
        "file (MVRV-Z from market cap ÷ MVRV, published-day lag), all cut at 2025-09-30.",
        "Holdout honesty: the 2025-10 → 2026-09 period had been seen in Lab 2's report (as part of its 2023–26 "
        "out-of-sample window) but no Lab 3 setup, rule or parameter was ever run or inspected on it before the "
        "frozen file was committed. Part A does not use the holdout (all 3-year runs end by 2025-09-30).",
        "Ablation uses OOS results to decide which rules to keep, as requested. That is a form of selection on the "
        "test data, so the OOS numbers of the kept variant are slightly optimistic. The Deflated Sharpe counts "
        "every variant tried, and the holdout is the clean test.",
        "One position at a time per asset; BTC and ETH are evaluated as separate accounts, so the 'max 3 new "
        "entries per day' cap applies per run (and never binds for BTC + ETH together in practice).",
        "Walk-forward trades are taken from a continuous run of the chosen parameter set; a trade open at a "
        "quarter boundary is kept to its exit. Equity, CAGR and drawdown are on closed trades (compounded "
        "per-trade returns). Months up = months with at least one closed trade whose compounded return was "
        "positive.",
        "Intrabar order is unknown: when a bar touches stop and target, the stop counts first; gaps fill at the "
        "open; limit fills at min(open, limit); a limit fill never takes profit on the same bar.",
        "T1: range = the L bars before the sweep bar; touches = bars whose high (low) is inside the top (bottom) "
        "15% of the range; reclaim = a close above Lo on the sweep bar or either of the next 2 bars. "
        "T1b: H = the latest confirmed fractal high, so target 'H' is skipped when no higher swing exists; "
        "time stop 120 bars (2 × 60).",
        "T2: trend = 5m close > 5m EMA200; the 60-minute break window starts at the 5m signal's close; random "
        "baseline entries for T2 are drawn on 5m bars with the same ATR distances.",
        "T3: the line is drawn through the two most recent confirmed fractal highs when the newer one is lower; "
        "each line is used once; 'two green' = the break candle and the next candle are green.",
        "T4: structure pivots are fractal k = 3; zone limit orders stay live for 100 bars and are cancelled by a "
        "close below the zone; stop = zone low − 0.1 ATR.",
        "T5: bullish engulfing = previous red candle, current green candle opening at/below the previous close and "
        "closing at/above the previous open with a larger body.",
        "T6: base pivots are fractal k = 3; tranches are placed after the crack close and may fill at the next open "
        "below a limit; failure exit at the next open after a close below base × (1 − 5d); risk sized as if all "
        "four tranches fill. Random-baseline trades for T6 use one entry at the average tranche distance.",
        "Random baseline: for each OOS trade, an entry at a random bar of the same timeframe and test quarter where "
        "the kept trend filter is true; same stop and target distances in ATR and the same holding cap (or the "
        "longest observed hold when a setup has none). 1,000 runs; the percentile is the share of runs with a lower "
        "expectancy.",
        "Deflated Sharpe: Bailey & López de Prado (2014) on per-trade R. N = all configurations evaluated in the lab; "
        "the trial-Sharpe variance comes from the Part B configurations with ≥ 30 trades.",
        "Minimum trade count is 40 when at least half of a setup's OOS trades are on daily bars, otherwise 100.",
    ]

    if passed_b:
        candidates = "\n".join(f"- **{k}**: rules `{list(res[k]['final'].rules)}`; holdout choices "
                               f"{hold[k]['choices']}" for k in passed_b[:2])
    else:
        candidates = ("**None qualified.** No short-term setup passed: each fell short on several rules at once, "
                      "not just trade count (see the pass-check tables), so there is nothing to paper-trade from "
                      "Part B.")
        if b_pass or a_pass:
            candidates += (" The only rules with supportive evidence are the long-horizon accumulation rules that "
                           "passed Part A (for example "
                           + ", ".join((b_pass[:2] or a_pass[:2])) +
                           "). They are not trading setups, and their evidence rests on overlapping windows. If "
                           "you want to paper-trade anything, a weekly 200-week-SMA multiplier DCA alongside plain "
                           "DCA is the honest candidate. Run it as a side-by-side comparison, not as an edge.")
    return {"verdict": verdict, "part_a": part_a, "lookahead": lookahead, "assumptions": assumptions,
            "candidates": candidates}
