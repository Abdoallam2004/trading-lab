"""Lab 2: BTC-centric halal strategies vs buy & hold and weekly DCA.

    python scripts/lab2_download.py   # once (needs Lab 1 data from scripts/download_data.py)
    python scripts/run_lab2.py

Writes reports/lab2_report.md, reports/lab2_equity.csv and reports/lab2_*.png
"""
from __future__ import annotations

import time

import _bootstrap  # noqa: F401
from lab.config import REPORTS_DIR
from lab2.evaluate import BENCH, IS, OOS, Evaluator, build_context, lookahead_check
from lab2.report import build_markdown, charts, equity_frame, param_str
from lab2.strategies import STRATEGIES

LOOKAHEAD_CUTOFFS = ["2019-06-16", "2021-11-08", "2024-03-11", "2026-09-28"]


def verdict(results, ev) -> str:
    """One blunt paragraph, built from the numbers."""
    a, b = ev.bench("A", OOS), ev.bench("B", OOS)
    lab = {f: {c.key: frs[f].label for c, frs in results.items()} for f in ("A", "B")}
    oos = {f: {c.key: frs[f].oos for c, frs in results.items()} for f in ("A", "B")}
    passes = [f"{k} (frame {f})" for f in lab for k, v in lab[f].items() if v == "PASS"]
    best_a = max(oos["A"], key=lambda k: oos["A"][k]["calmar"])
    low_dd_a = min((k for k in oos["A"] if k != "S7"), key=lambda k: oos["A"][k]["max_dd"])
    ties_b = [k for k, m in oos["B"].items() if abs(m["multiple"] - b["multiple"]) < 1e-6]
    best_b = max((k for k in oos["B"] if k not in ties_b), key=lambda k: oos["B"][k]["multiple"])
    s6 = oos["A"]["S6"]
    s7 = results[[c for c in results if c.key == "S7"][0]]["A"]
    txt = ("**No BTC-centric approach beat the simple benchmarks out-of-sample (2023-01 → 2026-09).** "
           if not passes else f"**Out-of-sample passes: {', '.join(passes)}.** ")
    txt += (f"Lump sum: buy & hold made Calmar {a['calmar']:.2f} (max drawdown {a['max_dd']:.0%}); the best strategy, "
            f"{best_a}, reached {oos['A'][best_a]['calmar']:.2f}, and the DCA-style rules (S2–S5) ended almost fully "
            f"invested, so they sat through the same {a['max_dd']:.0%} drawdown with less upside. The lowest drawdown "
            f"(apart from the mostly-cash S7) came from {low_dd_a}: {oos['A'][low_dd_a]['max_dd']:.0%}, in the market "
            f"{oos['A'][low_dd_a]['time_in_market']:.0%} of the time, but it gave up too much return "
            f"(Calmar {oos['A'][low_dd_a]['calmar']:.2f}). ")
    txt += (f"Weekly $100: plain DCA turned contributions into {b['multiple']:.2f}×; "
            + (f"{', '.join(ties_b)} matched it exactly, because their ×2/×3 multipliers can only spend a saved cash "
               f"reserve and in 2023–26 there were almost no 'expensive' weeks to save in; " if ties_b else "")
            + f"the best non-tied rule, {best_b}, made {oos['B'][best_b]['multiple']:.2f}× with a "
            f"{oos['B'][best_b]['max_dd']:.0%} drawdown (vs {b['max_dd']:.0%}) and "
            f"{oos['B'][best_b]['btc_per_1k'] / b['btc_per_1k']:.0%} of DCA's BTC per dollar — less risk, but not "
            f"more money. ")
    txt += (f"Alt momentum rotation inside BTC uptrends (S6) was the worst idea tested: {s6['cagr']:.0%} a year with a "
            f"{s6['max_dd']:.0%} drawdown, confirming Lab 1. The Fibonacci pullback (S7) took only {s7.oos_trades} "
            f"out-of-sample trades, too few to judge (INCONCLUSIVE), and lost money on them "
            f"({s7.oos['cagr']:.1%} a year). Several rules looked better than the benchmarks in-sample (2018–22 "
            f"bear-heavy) and lost that edge after 2022 — the textbook overfitting pattern. Practical read: the bar to "
            f"beat is still plain buy & hold / weekly DCA; drawdown filters (S1, S3) buy a smaller drawdown with "
            f"lower returns, which these pass rules count as a failure.")
    return txt


def main():
    t0 = time.time()
    ctx, prices = build_context()
    ev = Evaluator(ctx, prices)
    results = {}
    for cls in STRATEGIES:
        results[cls] = ev.evaluate(cls)
    print(f"evaluated in {time.time() - t0:.0f}s; look-ahead check on real data ...")
    items = [(cls, frs[f].chosen) for cls, frs in results.items() for f in ("A", "B")]
    items = list({(c, tuple(sorted(p.items()))): (c, p) for c, p in items}.values())
    look = lookahead_check(items, LOOKAHEAD_CUTOFFS)
    print(f"look-ahead: {sum(r['ok'] for r in look)}/{len(look)} identical")

    notes = {"verdict": verdict(results, ev), "assumptions": ASSUMPTIONS}
    REPORTS_DIR.mkdir(exist_ok=True)
    md = build_markdown(results, ev, look, notes)
    (REPORTS_DIR / "lab2_report.md").write_text(md)
    eq = equity_frame(results, ev)
    eq.to_csv(REPORTS_DIR / "lab2_equity.csv", index=False)
    for p in charts(eq, results, REPORTS_DIR):
        print("chart", p)
    for cls, frs in results.items():
        print(f"{cls.key:<5} A: {frs['A'].label:<12} {param_str(frs['A'].chosen):<28} "
              f"B: {frs['B'].label:<12} {param_str(frs['B'].chosen)}")
    print(f"done in {time.time() - t0:.0f}s -> {REPORTS_DIR / 'lab2_report.md'}")


ASSUMPTIONS = [
    "**Prices & trading**: Binance spot BTCUSDT/ETHUSDT daily klines from 2017-08-17 (data.binance.vision, via its "
    "S3 bucket) merged with Lab 1's cache. Trades start 2018-01-01. Decisions use closes up to day t−1 and fill at "
    "day t's open; weekly strategies decide on the Sunday close and trade at Monday's open. Every fill pays 0.10% fee "
    "+ 0.05% slippage; idle cash earns 0%; buys are capped at cash (no leverage), sells at holdings (no shorting).",
    "**Long-history signals**: CoinMetrics community `PriceUSD` (2010-07-18 →) is spliced before Binance's first bar and "
    "used only for signals (200-week SMA, log regression, all-time high before 2017-08). Days since genesis count "
    "from 2009-01-03; the log-regression needs ≥ 4 years of data and is refit on the 1st of each month using only "
    "earlier data.",
    "**MVRV-Z (S5)**: the free CoinMetrics file has no `CapRealUSD`, but it has `CapMVRVCur` (= market cap ÷ realized "
    "cap) and `CapMrktCurUSD`, so realized cap = market cap ÷ MVRV exactly. MVRV-Z = (market cap − realized cap) ÷ "
    "expanding std of market cap (≥ 365 days). All on-chain values are lagged one day (publication delay). "
    "**Gap:** the free file ends 2026-05-23; for 2026-05-24 → 2026-09-30 market cap = Binance close × last known "
    "supply and realized cap is carried forward unchanged (an approximation for the last ~4 months of OOS).",
    "**Frame A for DCA-style strategies (S2, S4, S5)**: the $10,000 is a cash reserve; the base weekly buy is "
    "$10,000 ÷ 104 (a 2-year plan at ×1) and multipliers scale it. S3 in frame A deploys the reserve over N weeks "
    "once the drawdown trigger fires.",
    "**Frame B**: $100 arrives every Monday. Unspent money waits in a 0% reserve; ×2/×3 multipliers can only spend "
    "what the reserve holds, so a run that starts with an empty reserve (every OOS and cycle run starts fresh) "
    "cannot over-buy until it has saved. This is why S4 and S5 are identical to plain DCA out-of-sample: S4's z-score "
    "never went above +1σ in 2023-26 (no ×0 weeks to build a reserve) and MVRV-Z was below 0 on only 1% of days.",
    "**Trims** (S2 10% above its table's level, S4 15% above +trim_z σ, S5 15% above K) happen at most once every "
    "4 weeks while the condition holds; proceeds go to the cash reserve.",
    "**S3**: when the drawdown first reaches X, the reserve saved so far is split into N equal weekly extra buys; "
    "buying stops (and the reserve rebuilds) whenever the drawdown is back under X.",
    "**S4 grid**: the spec fixes the bands, so the only grid dimension is the trim level (+1.5σ / +2σ spec / +2.5σ).",
    "**S6 universe**: Lab 1's point-in-time halal top 50 (prior-3-month USDT volume, re-ranked monthly, delisted coins "
    "included, redenominations split), extended back to 2017-08 with every eligible pair's early archive "
    "(71 pairs traded before 2019-10). BTC itself is excluded from the alt list. Holdings of a coin that stops trading "
    "are sold at its last close. Weekly rebalance skips drifts under 1% of equity.",
    "**S7**: daily bars; ZigZag pivots are confirmed only after a move of the threshold (no repainting); a setup is "
    "live from the bar after the swing high is confirmed until the next pivot is confirmed; limit entry at the 61.8% "
    "retracement (fill at the open if it gaps below), stop 0.5% under the 78.6% level, target the swing high; "
    "same-bar stop assumed first; regime = BTC close > 200-day SMA (S1). Positions are sized to lose 1.5% of equity "
    "at the stop, capped by cash.",
    "**Metrics**: max drawdown, Calmar and Sharpe use the time-weighted return index (investor contributions removed); "
    "Calmar = annualised TWR ÷ max drawdown; Sharpe uses daily returns × √365 with a 0% risk-free rate; IRR is the "
    "money-weighted return of the actual contributions; turnover = traded notional ÷ average equity per year.",
    "**Pass rules as applied**: Frame A: OOS Calmar > B1's and OOS max DD ≤ B1's. Frame B: OOS (value ÷ contributed "
    "> B2's or BTC per $ > B2's) and OOS max DD ≤ B2's. Robustness: ≥ 70% of grid neighbours (one step in one "
    "dimension) must also pass that OOS test. Profit concentration uses the full-period run (the OOS window has only "
    "two cycle segments): no cycle may contribute > 60% of total profit. Strategies that pass the OOS comparison but "
    "fail robustness/concentration are INCONCLUSIVE; S7 with < 30 OOS trades is INCONCLUSIVE (insufficient data).",
    "**Parameters were chosen only on 2018–2022** (frame A: best in-sample Calmar; frame B: best in-sample value ÷ "
    "contributed; among sets whose in-sample drawdown ≤ the benchmark's when any exist). The OOS run used those "
    "parameters once; neighbours' OOS results are reported for the robustness rule only, never for selection.",
]


if __name__ == "__main__":
    main()
