"""Markdown report + machine-readable list of strategies that passed out-of-sample."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .metrics import group_stats
from .walkforward import Criteria, StrategyWF


def _f(x, kind="num"):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "-"
    if kind == "pct":
        return f"{x:.1%}"
    if kind == "r":
        return f"{x:+.3f}R"
    if kind == "usd":
        return f"{x:+,.0f}$"
    if kind == "pf":
        return "inf" if x == np.inf else f"{x:.2f}"
    if kind == "int":
        return f"{int(x)}"
    return f"{x:.2f}"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def _stats_table(df: pd.DataFrame, first: str) -> str:
    if df is None or len(df) == 0:
        return "_no trades_"
    rows = [[k, _f(r["trades"], "int"), _f(r["win_rate"], "pct"), _f(r["profit_factor"], "pf"),
             _f(r["expectancy_r"], "r"), _f(r["expectancy_usd"], "usd"), _f(r["pnl"], "usd")]
            for k, r in df.iterrows()]
    return _table([first, "Trades", "Win rate", "Profit factor", "Expectancy", "Exp. $/trade", "Net P&L"], rows)


def build_markdown(results: list[StrategyWF], meta: dict, criteria: Criteria = Criteria()) -> str:
    L: list[str] = []
    synthetic = meta.get("data_source") == "synthetic"
    L.append("# Halal Spot Crypto Backtest Report\n")
    if synthetic:
        L.append("> ⚠️ **SYNTHETIC DATA. These numbers are a software smoke test on random prices "
                 "and say nothing about real markets. Do not trade on them.**\n")
    L.append(f"Generated {meta.get('generated', datetime.now(timezone.utc).isoformat(timespec='minutes'))}  ")
    pit = meta.get("pit") or {}
    uni_txt = (f"point-in-time top {meta.get('top_n', 50)} (re-ranked by prior {meta.get('lookback_months', 3)}-month "
               f"volume at the start of every period; {len(meta.get('symbols', []))} distinct coins over time)"
               if pit else f"{len(meta.get('symbols', []))} coins (fixed list)")
    L.append(f"Data: {meta.get('data_source')} · {meta.get('data_start')} → {meta.get('data_end')} · "
             f"{uni_txt} · timeframes {', '.join(meta.get('timeframes', []))}  ")
    L.append(f"Rules: spot only, long only, no leverage, no shorting · fees {meta['fee']:.2%}/side + "
             f"slippage {meta['slippage']:.2%}/fill · risk {meta['risk']:.1%} of equity per trade · "
             f"max {meta['max_pos']:.0%} of equity per coin · one position per coin  ")
    L.append(f"Walk-forward: optimise on {meta['train_months']} months, test on the next "
             f"{meta['test_months']} unseen months, roll forward. "
             f"Pass bar (OOS): ≥{criteria.min_trades} trades, PF ≥ {criteria.min_profit_factor}, "
             f"expectancy ≥ {criteria.min_expectancy_r}R, max DD ≤ {criteria.max_drawdown:.0%}, "
             f"positive in ≥ {criteria.min_positive_window_frac:.0%} of OOS windows.\n")

    L.append("## 1. Ranking by out-of-sample results\n")
    rows = []
    for i, r in enumerate(results, 1):
        o = r.oos
        rows.append([i, f"**{r.strategy}**", "✅ PASS" if r.verdict == "PASS" else "❌ FAIL",
                     _f(o.get("trades"), "int"), _f(o.get("win_rate"), "pct"), _f(o.get("profit_factor"), "pf"),
                     _f(o.get("expectancy_r"), "r"), _f(o.get("expectancy_usd"), "usd"),
                     _f(o.get("max_drawdown"), "pct"), _f(o.get("total_return"), "pct"),
                     _f(r.is_.get("expectancy_r"), "r"), len(r.flags)])
    L.append(_table(["#", "Strategy", "Verdict", "OOS trades", "Win rate", "Profit factor", "Expectancy",
                     "Exp. $/trade", "Max DD", "OOS return", "In-sample exp.", "Overfit flags"], rows))
    L.append("\nExpectancy is the average result per trade in R (1R = the amount risked). "
             "\"In-sample exp.\" is what the optimiser saw on its training windows; a big gap to OOS = overfitting.\n")

    L.append("### Baseline: the exact specified rules, no optimisation (same OOS periods, daily, exit 2R/3R)\n")
    rows = [[r.strategy, _f(r.spec.get("trades"), "int"), _f(r.spec.get("win_rate"), "pct"),
             _f(r.spec.get("profit_factor"), "pf"), _f(r.spec.get("expectancy_r"), "r"),
             _f(r.spec.get("max_drawdown"), "pct"), _f(r.spec.get("total_return"), "pct")] for r in results]
    L.append(_table(["Strategy", "Trades", "Win rate", "Profit factor", "Expectancy", "Max DD", "Return"], rows))
    L.append("")

    L.append("## 2. Verdicts and overfitting flags\n")
    for r in results:
        L.append(f"### {r.strategy}: {r.verdict}\n")
        L.append(f"- Configs searched per window: {r.n_configs} (more configs = more chances to fit noise)")
        for x in r.reasons:
            L.append(f"- ❌ {x}")
        for x in r.flags:
            L.append(f"- 🚩 {x}")
        if not r.reasons and not r.flags:
            L.append("- No failure reasons, no overfitting flags.")
        if r.live_config is not None:
            L.append(f"- Config for live scanning (best on the latest {meta['train_months']} months): `{r.live_config.label}`")
        L.append("")

    L.append("## 3. Details per strategy\n")
    for r in results:
        L.append(f"### {r.strategy}\n")
        L.append("**Walk-forward windows**\n")
        rows = []
        for w in r.windows:
            tr, te = w["train"] or {}, w["test"]
            rows.append([w["window"], f"`{w['chosen']}`", _f(tr.get("trades"), "int"), _f(tr.get("expectancy_r"), "r"),
                         _f(te.get("trades"), "int"), _f(te.get("expectancy_r"), "r"), _f(te.get("profit_factor"), "pf"),
                         _f(w["test_median_cfg_exp_r"], "r"), _f(w["test_frac_cfg_positive"], "pct")])
        L.append(_table(["Window", "Chosen config", "Train trades", "Train exp.", "Test trades", "Test exp.",
                         "Test PF", "Median config test exp.", "Configs positive in test"], rows))
        L.append("\n**By market regime (OOS)**\n")
        L.append(_stats_table(r.by("regime"), "Regime"))
        L.append("\n**By market regime (spec rules, full history)**\n")
        L.append(_stats_table(r.by("regime", "spec_full"), "Regime"))
        L.append("\n**By year (OOS)**\n")
        L.append(_stats_table(r.by("year"), "Year"))
        L.append("\n**By year (spec rules, full history 2020→, not walk-forward)**\n")
        L.append(_stats_table(r.by("year", "spec_full"), "Year"))
        L.append("\n**By coin (OOS, sorted by net P&L)**\n")
        coin = r.by("symbol")
        L.append(_stats_table(coin.sort_values("pnl", ascending=False) if len(coin) else coin, "Coin"))
        L.append("")

    if pit:
        L.append("## 4. Point-in-time universe\n")
        L.append("Each period trades only the coins that were the top by USDT volume over the 3 months *before* "
                 "it started (excluded categories removed). Coins added / dropped versus the previous snapshot:\n")
        current = set(meta.get("current_universe", []))
        rows, prev = [], None
        for d, syms in pit.items():
            added = sorted(set(syms) - set(prev)) if prev is not None else []
            dropped = sorted(set(prev) - set(syms)) if prev is not None else []
            rows.append([d, len(syms), ", ".join(added) or "-", ", ".join(dropped) or "-"])
            prev = syms
        L.append(_table(["Period start", "Coins", "Added", "Dropped"], rows))
        gone = sorted(set(meta.get("symbols", [])) - current)
        L.append(f"\nCoins traded in some period that are **not** in today's top {meta.get('top_n', 50)} "
                 f"({len(gone)}): {', '.join(gone) or '-'}\n")
        L.append(f"First snapshot: {', '.join(next(iter(pit.values())))}\n")
    if meta.get("excluded"):
        L.append("## 5. Excluded pairs\n")
        for reason, syms in meta["excluded"].items():
            L.append(f"- **{reason}** ({len(syms)}): {', '.join(syms)}")
        L.append("")

    L.append("## 6. Caveats\n")
    if pit:
        L.append("- **Survivorship bias** is addressed with the point-in-time universe above. Coins delisted while "
                 "a position was open are closed at their last traded price.")
    else:
        L.append("- **Survivorship bias:** the universe is today's top coins by volume. Coins that collapsed or were "
                 "delisted since 2020 are missing, so every result is somewhat optimistic.")
    L.append("- Token redenominations / relaunches (e.g. COCOS x1000, LUNA → LUNA 2.0, QUICK /1000) are split into "
             "separate assets (`SYMBOL~YYYYMMDD` = the old token, ending that day); no trade spans the swap.")
    L.append("- Profit factor and max drawdown are in dollars on a compounding account, so a losing streak early "
             "(e.g. 2022) weighs more than later wins; expectancy in R is the size-independent measure.")
    L.append("- Flash-crash wicks (e.g. 10 Oct 2025) fill stops at the stop price; real fills would have been worse.")
    L.append("- Intrabar order is unknown on OHLC bars; when a bar touches both stop and target the stop is assumed first "
             "(conservative). Gaps through a level fill at the open.")
    L.append("- When cash runs short, simultaneous signals are filled in alphabetical order.")
    L.append("- Past performance, even out-of-sample, does not guarantee future results. Paper-trade before going live.")
    if synthetic:
        L.append("- **This run used synthetic random data.** Run `python scripts/download_data.py` on a machine that "
                 "can reach data.binance.vision, then re-run the backtest.")
    return "\n".join(L) + "\n"


def passed_payload(results: list[StrategyWF], meta: dict) -> dict:
    out = []
    for r in results:
        if r.verdict != "PASS" or r.live_config is None:
            continue
        reg = group_stats(r.oos_trades, "regime") if len(r.oos_trades) else pd.DataFrame()
        out.append({
            "strategy": r.strategy,
            "config": r.live_config.to_dict(),
            "oos": {k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in r.oos.items()},
            "oos_by_regime": {k: {"trades": int(v["trades"]), "expectancy_r": float(v["expectancy_r"])}
                              for k, v in reg.iterrows()},
            "flags": r.flags,
        })
    return {"generated": meta.get("generated"), "data_source": meta.get("data_source"),
            "data_end": meta.get("data_end"), "strategies": out}
