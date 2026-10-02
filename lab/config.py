"""Central configuration: paths, costs, risk model."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"

START_DATE = "2020-01-01"
INTERVALS = ("1d", "4h")
TOP_N = 50
QUOTE = "USDT"


@dataclass(frozen=True)
class CostModel:
    fee_rate: float = 0.001      # 0.1% per side
    slippage: float = 0.0005     # 0.05% adverse price per fill


@dataclass(frozen=True)
class RiskModel:
    initial_capital: float = 10_000.0
    risk_per_trade: float = 0.015    # 1.5% of equity lost if the stop is hit
    max_position_frac: float = 0.40  # max 40% of equity in one coin
    min_notional: float = 10.0       # Binance-like minimum order size
