"""Performance statistics."""
from __future__ import annotations

import numpy as np
import pandas as pd


def max_drawdown(equity: pd.Series) -> float:
    """Largest peak-to-trough decline as a positive fraction (0.25 = -25%)."""
    if len(equity) == 0:
        return 0.0
    peak = equity.cummax()
    return float(((peak - equity) / peak).max())


def profit_factor(pnl: pd.Series) -> float:
    gains = pnl[pnl > 0].sum()
    losses = -pnl[pnl < 0].sum()
    if losses == 0:
        return float("inf") if gains > 0 else float("nan")
    return float(gains / losses)


def trade_stats(trades: pd.DataFrame) -> dict:
    n = len(trades)
    if n == 0:
        return {"trades": 0, "win_rate": np.nan, "profit_factor": np.nan, "expectancy_r": np.nan,
                "expectancy_usd": np.nan, "avg_win_r": np.nan, "avg_loss_r": np.nan, "pnl": 0.0}
    pnl, r = trades["pnl"], trades["r_multiple"]
    return {
        "trades": n,
        "win_rate": float((pnl > 0).mean()),
        "profit_factor": profit_factor(pnl),
        "expectancy_r": float(r.mean()),
        "expectancy_usd": float(pnl.mean()),
        "avg_win_r": float(r[r > 0].mean()) if (r > 0).any() else np.nan,
        "avg_loss_r": float(r[r <= 0].mean()) if (r <= 0).any() else np.nan,
        "pnl": float(pnl.sum()),
    }


def summarize(trades: pd.DataFrame, equity: pd.Series, initial_capital: float) -> dict:
    out = trade_stats(trades)
    final = float(equity.iloc[-1]) if len(equity) else initial_capital
    out["total_return"] = final / initial_capital - 1
    out["max_drawdown"] = max_drawdown(pd.concat([pd.Series([initial_capital]), equity.reset_index(drop=True)]))
    years = (equity.index[-1] - equity.index[0]).days / 365.25 if len(equity) > 1 else 0
    out["cagr"] = (final / initial_capital) ** (1 / years) - 1 if years > 0.25 and final > 0 else np.nan
    return out


def group_stats(trades: pd.DataFrame, by) -> pd.DataFrame:
    """trade_stats per group (coin, year, regime ...)."""
    if len(trades) == 0:
        return pd.DataFrame()
    rows = {k: trade_stats(g) for k, g in trades.groupby(by)}
    return pd.DataFrame.from_dict(rows, orient="index").drop(columns=["avg_win_r", "avg_loss_r"])
