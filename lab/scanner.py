"""Daily scanner: apply only the strategies that passed out-of-sample to the latest closed bars."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import CostModel, RiskModel
from .data import drop_unclosed
from .indicators import add_indicators
from .regime import current_regime
from .strategies import StrategyConfig, signal_mask, stop_levels

SCAN_COLUMNS = ["strategy", "timeframe", "symbol", "bar_time", "entry_ref", "stop", "risk_pct",
                "target_2R", "target_3R", "exit_plan", "qty", "notional", "regime", "oos_exp_in_regime"]


def size_position(equity: float, entry: float, stop: float, risk: RiskModel, costs: CostModel) -> tuple[float, float]:
    per_unit = entry * (1 + costs.slippage) * (1 + costs.fee_rate) - stop * (1 - costs.slippage) * (1 - costs.fee_rate)
    qty = risk.risk_per_trade * equity / per_unit
    notional = min(qty * entry, risk.max_position_frac * equity)
    return notional / entry, notional


def scan(passed: dict, frames: dict[str, dict[str, pd.DataFrame]], btc_daily: pd.DataFrame | None,
         equity: float, risk: RiskModel = RiskModel(), costs: CostModel = CostModel(),
         now: pd.Timestamp | None = None, regime_filter: bool = False,
         max_age: pd.Timedelta = pd.Timedelta(hours=36)) -> tuple[pd.DataFrame, list[str]]:
    """Return (signals, warnings). frames[tf][symbol] = raw OHLCV."""
    now = now or pd.Timestamp.now(tz="UTC")
    regime = current_regime(btc_daily) if btc_daily is not None and len(btc_daily) else "unknown"
    rows, warnings = [], []
    for item in passed.get("strategies", []):
        cfg = StrategyConfig.from_dict(item["config"])
        reg_stats = item.get("oos_by_regime", {}).get(regime)
        reg_exp = reg_stats["expectancy_r"] if reg_stats else np.nan
        if regime_filter and not (np.isfinite(reg_exp) and reg_exp > 0):
            warnings.append(f"{cfg.strategy}: skipped, OOS expectancy in regime {regime} is not positive")
            continue
        bar = pd.Timedelta(cfg.timeframe.replace("d", "D"))
        for sym, raw in frames.get(cfg.timeframe, {}).items():
            df = drop_unclosed(raw, cfg.timeframe, now)
            if len(df) < 250:
                continue
            if now - (df.index[-1] + bar) > max(max_age, 2 * bar):  # the archive lags ~1 day
                warnings.append(f"{sym} {cfg.timeframe}: data is stale (last bar {df.index[-1]:%Y-%m-%d %H:%M})")
                continue
            d = add_indicators(df)
            if not bool(signal_mask(d, cfg.strategy, cfg.p).iloc[-1]):
                continue
            entry = float(d["close"].iloc[-1])
            stop = float(stop_levels(d, cfg.p["swing"]).iloc[-1])
            if not np.isfinite(stop) or stop >= entry:
                continue
            r = entry - stop
            qty, notional = size_position(equity, entry, stop, risk, costs)
            rows.append({
                "strategy": cfg.strategy, "timeframe": cfg.timeframe, "symbol": sym,
                "bar_time": d.index[-1], "entry_ref": entry, "stop": stop, "risk_pct": r / entry,
                "target_2R": entry + 2 * r, "target_3R": entry + 3 * r, "exit_plan": cfg.exit.label,
                "qty": qty, "notional": notional, "regime": regime, "oos_exp_in_regime": reg_exp,
            })
    return pd.DataFrame(rows, columns=SCAN_COLUMNS), list(dict.fromkeys(warnings))


def to_markdown(signals: pd.DataFrame, warnings: list[str], passed: dict, equity: float, now: pd.Timestamp) -> str:
    L = [f"# Daily scan {now:%Y-%m-%d %H:%M} UTC\n",
         "Spot only · long only · no leverage. Enter at the next open only if price is still above the stop.\n",
         f"Strategies used (passed out-of-sample): "
         f"{', '.join(s['strategy'] + ' ' + s['config']['timeframe'] for s in passed.get('strategies', [])) or 'none'}  ",
         f"Account equity for sizing: {equity:,.0f} USDT\n"]
    if passed.get("data_source") == "synthetic":
        L.append("> ⚠️ The strategy list came from a SYNTHETIC-data backtest. Do not trade it.\n")
    if len(signals) == 0:
        L.append("No signals today.")
    else:
        L.append("| Strategy | TF | Coin | Entry ref | Stop | Risk % | 2R | 3R | Exit plan | Qty | Notional $ | OOS exp. in current regime |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for s in signals.itertuples():
            L.append(f"| {s.strategy} | {s.timeframe} | {s.symbol} | {s.entry_ref:.6g} | {s.stop:.6g} | {s.risk_pct:.1%} | "
                     f"{s.target_2R:.6g} | {s.target_3R:.6g} | {s.exit_plan} | {s.qty:.6g} | {s.notional:,.0f} | "
                     f"{'-' if not np.isfinite(s.oos_exp_in_regime) else f'{s.oos_exp_in_regime:+.2f}R'} ({s.regime}) |")
    if warnings:
        L.append("\n**Warnings**\n")
        L += [f"- {w}" for w in warnings]
    return "\n".join(L) + "\n"
