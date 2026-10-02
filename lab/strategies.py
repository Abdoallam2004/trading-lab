"""Entry rules. Every rule is evaluated on a *closed* bar; the engine enters at the next open.

PULLBACK  uptrend (EMA50 > EMA200), close within k*ATR of EMA20 or EMA50, RSI in [lo, hi]
BREAKOUT  close > highest high of the previous N bars, volume >= m x 20-bar average volume
BASE      EMA50 below EMA200 (still in a base), close reclaims EMA50 (crosses above),
          ADX rising over the last k bars and >= adx_min
Stop      lowest low of the last `swing` bars - 0.5 ATR
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .engine import EXIT_MODES, ExitConfig, Setup

STRATEGIES = ("PULLBACK", "BREAKOUT", "BASE")

# Exactly the rules as specified; the walk-forward grid explores small variations around them.
SPEC_PARAMS = {
    "PULLBACK": {"rsi_lo": 38, "rsi_hi": 58, "prox_atr": 1.0, "swing": 10},
    "BREAKOUT": {"lookback": 20, "vol_mult": 1.5, "swing": 10},
    "BASE": {"adx_rise": 3, "adx_min": 15, "swing": 10},
}

PARAM_GRID = {
    "PULLBACK": {"rsi": [(38, 58), (40, 55)], "prox_atr": [0.5, 1.0], "swing": [10]},
    "BREAKOUT": {"lookback": [20], "vol_mult": [1.5, 2.0], "swing": [10, 20]},
    "BASE": {"adx_rise": [3, 5], "adx_min": [15, 20], "swing": [10]},
}

EXIT_GRID = [ExitConfig("2R"), ExitConfig("3R"), ExitConfig("2R_3R"), ExitConfig("trail", 3.0)]
STOP_ATR_MULT = 0.5


@dataclass(frozen=True)
class StrategyConfig:
    strategy: str
    timeframe: str
    params: tuple                 # sorted (name, value) pairs -> hashable
    exit: ExitConfig = ExitConfig()

    @classmethod
    def make(cls, strategy: str, timeframe: str, params: dict, exit: ExitConfig = ExitConfig()):
        if strategy not in STRATEGIES:
            raise ValueError(f"unknown strategy {strategy}")
        return cls(strategy, timeframe, tuple(sorted(params.items())), exit)

    @property
    def p(self) -> dict:
        return dict(self.params)

    @property
    def signal_key(self) -> tuple:
        return (self.strategy, self.timeframe, self.params)

    @property
    def label(self) -> str:
        ps = " ".join(f"{k}={v}" for k, v in self.params)
        return f"{self.strategy} {self.timeframe} [{ps}] exit={self.exit.label}"

    def to_dict(self) -> dict:
        return {"strategy": self.strategy, "timeframe": self.timeframe, "params": self.p,
                "exit_mode": self.exit.mode, "trail_atr_mult": self.exit.trail_atr_mult}

    @classmethod
    def from_dict(cls, d: dict) -> "StrategyConfig":
        return cls.make(d["strategy"], d["timeframe"], d["params"],
                        ExitConfig(d["exit_mode"], d.get("trail_atr_mult", 3.0)))


def _expand(strategy: str) -> list[dict]:
    grid = PARAM_GRID[strategy]
    out = []
    for combo in itertools.product(*grid.values()):
        d = dict(zip(grid.keys(), combo))
        if "rsi" in d:
            d["rsi_lo"], d["rsi_hi"] = d.pop("rsi")
        out.append(d)
    return out


def config_grid(strategy: str, timeframes=("1d", "4h"), exits=None) -> list[StrategyConfig]:
    exits = EXIT_GRID if exits is None else exits
    return [StrategyConfig.make(strategy, tf, p, ex)
            for tf in timeframes for p in _expand(strategy) for ex in exits]


def signal_mask(d: pd.DataFrame, strategy: str, p: dict) -> pd.Series:
    """Boolean entry signal per bar. `d` must come from indicators.add_indicators."""
    c = d["close"]
    if strategy == "PULLBACK":
        band = p["prox_atr"] * d["atr"]
        near = ((c - d["ema20"]).abs() <= band) | ((c - d["ema50"]).abs() <= band)
        sig = (d["ema50"] > d["ema200"]) & near & d["rsi"].between(p["rsi_lo"], p["rsi_hi"])
    elif strategy == "BREAKOUT":
        n = p["lookback"]
        prev_high = d["high20_prev"] if n == 20 else d["high"].rolling(n, min_periods=n).max().shift(1)
        sig = (c > prev_high) & (d["volume"] >= p["vol_mult"] * d["vol_avg20"])
    elif strategy == "BASE":
        k = p["adx_rise"]
        reclaim = (c > d["ema50"]) & (c.shift(1) <= d["ema50"].shift(1))
        sig = (d["ema50"] < d["ema200"]) & reclaim & (d["adx"] > d["adx"].shift(k)) & (d["adx"] >= p["adx_min"])
    else:
        raise ValueError(strategy)
    valid = d[["ema200", "atr", "rsi", "adx"]].notna().all(axis=1)
    return (sig & valid).fillna(False).astype(bool)


def stop_levels(d: pd.DataFrame, swing: int, atr_mult: float = STOP_ATR_MULT) -> pd.Series:
    """Recent swing low (lowest low of the last `swing` bars incl. the signal bar) minus 0.5 ATR."""
    return d["low"].rolling(swing, min_periods=swing).min() - atr_mult * d["atr"]


def make_setup(d: pd.DataFrame, cfg: StrategyConfig) -> Setup:
    p = cfg.p
    sig = signal_mask(d, cfg.strategy, p).to_numpy()
    stops = stop_levels(d, p["swing"]).to_numpy()
    idx = np.flatnonzero(sig & np.isfinite(stops))
    return Setup(idx, stops[idx])


assert set(EXIT_MODES) == {e.mode for e in EXIT_GRID}
