"""Long-only spot backtest engine (no leverage, no shorting).

Two layers:
  1. TradeSimulator: given a signal on bar i, enter at the open of bar i+1 and
     walk forward bar by bar to find the exit fills (stop / targets / trailing).
     Conservative intrabar rule: if a bar touches both the stop and a target,
     the stop is assumed to fill first. Gaps through a level fill at the open.
  2. run_portfolio: walks all candidate entries in time order across coins,
     sizes each trade at 1.5% equity risk from the stop distance, caps it at
     40% of equity and at available cash (no leverage), keeps at most one
     position per coin, and builds the equity curve.
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import CostModel, RiskModel

EXIT_MODES = ("2R", "3R", "2R_3R", "trail")


@dataclass(frozen=True)
class ExitConfig:
    mode: str = "2R_3R"          # 2R | 3R | 2R_3R (half at 2R, stop->breakeven, rest at 3R) | trail
    trail_atr_mult: float = 3.0  # chandelier: highest high since entry - k * ATR

    def __post_init__(self):
        if self.mode not in EXIT_MODES:
            raise ValueError(f"unknown exit mode {self.mode}")

    @property
    def label(self) -> str:
        return f"trail{self.trail_atr_mult:g}ATR" if self.mode == "trail" else self.mode


@dataclass
class Fill:
    time: int      # bar open_time in ns
    frac: float    # fraction of the original quantity sold
    price: float   # executed price (after slippage)
    reason: str


@dataclass
class SimTrade:
    symbol: str
    signal_idx: int
    entry_idx: int
    entry_time: int
    entry_price: float   # executed (after slippage)
    stop: float
    fills: list[Fill]

    @property
    def exit_time(self) -> int:
        return self.fills[-1].time


class SymbolData:
    """Numpy view of one symbol's OHLC + ATR."""

    def __init__(self, symbol: str, df: pd.DataFrame):
        self.symbol = symbol
        idx = df.index if df.index.tz is not None else df.index.tz_localize("UTC")
        self.index = idx.tz_convert("UTC").as_unit("ns")
        self.times = self.index.asi8
        self.open = df["open"].to_numpy(float)
        self.high = df["high"].to_numpy(float)
        self.low = df["low"].to_numpy(float)
        self.close = df["close"].to_numpy(float)
        self.atr = df["atr"].to_numpy(float) if "atr" in df else np.full(len(df), np.nan)

    def __len__(self) -> int:
        return len(self.times)

    def last_idx_before(self, t: int) -> int:
        """Index of the last bar with open_time < t (-1 if none)."""
        return int(np.searchsorted(self.times, t, side="left")) - 1


def simulate_trade(sd: SymbolData, signal_idx: int, stop: float, exit_cfg: ExitConfig,
                   costs: CostModel) -> SimTrade | None:
    e = signal_idx + 1
    if e >= len(sd) or not np.isfinite(stop) or stop <= 0:
        return None
    raw_entry = sd.open[e]
    if stop >= raw_entry:
        return None  # price already below the stop at the open: no trade
    slip = costs.slippage
    entry = raw_entry * (1 + slip)
    r = entry - stop
    mode = exit_cfg.mode
    if mode == "2R":
        targets = [(entry + 2 * r, 1.0, "target_2R")]
    elif mode == "3R":
        targets = [(entry + 3 * r, 1.0, "target_3R")]
    elif mode == "2R_3R":
        targets = [(entry + 2 * r, 0.5, "target_2R"), (entry + 3 * r, 0.5, "target_3R")]
    else:
        targets = []
    cur_stop = stop
    remaining = 1.0
    fills: list[Fill] = []
    highest = -np.inf
    n = len(sd)
    for j in range(e, n):
        o, h, lo = sd.open[j], sd.high[j], sd.low[j]
        t = int(sd.times[j])
        if lo <= cur_stop:
            px = min(o, cur_stop) * (1 - slip)
            reason = "stop" if cur_stop <= stop else ("breakeven" if mode == "2R_3R" else "trail_stop")
            fills.append(Fill(t, remaining, px, reason))
            remaining = 0.0
            break
        hit_partial = False
        while targets and h >= targets[0][0]:
            level, frac, reason = targets.pop(0)
            frac = min(frac, remaining)
            fills.append(Fill(t, frac, max(o, level) * (1 - slip), reason))
            remaining -= frac
            hit_partial = True
        if remaining <= 1e-12:
            remaining = 0.0
            break
        if hit_partial and mode == "2R_3R":
            cur_stop = max(cur_stop, entry)  # breakeven from the next bar
        if mode == "trail":
            highest = max(highest, h)
            a = sd.atr[j]
            if np.isfinite(a):
                cur_stop = max(cur_stop, highest - exit_cfg.trail_atr_mult * a)
    if remaining > 0:
        fills.append(Fill(int(sd.times[-1]), remaining, sd.close[-1] * (1 - slip), "end_of_data"))
    return SimTrade(sd.symbol, signal_idx, e, int(sd.times[e]), entry, stop, fills)


def truncate_trade(tr: SimTrade, sd: SymbolData, end: int, costs: CostModel) -> SimTrade:
    """Force-close whatever is still open at the window end (close of the last bar before `end`)."""
    if tr.exit_time < end:
        return tr
    kept = [f for f in tr.fills if f.time < end]
    remaining = 1.0 - sum(f.frac for f in kept)
    j = sd.last_idx_before(end)
    if remaining > 1e-12:
        kept.append(Fill(int(sd.times[j]), remaining, sd.close[j] * (1 - costs.slippage), "window_end"))
    return SimTrade(tr.symbol, tr.signal_idx, tr.entry_idx, tr.entry_time, tr.entry_price, tr.stop, kept)


@dataclass
class Setup:
    """A strategy's output for one symbol: signal bars and their stop levels."""
    signal_idx: np.ndarray
    stops: np.ndarray


@dataclass
class BacktestResult:
    trades: pd.DataFrame
    equity: pd.Series
    initial_capital: float
    start: pd.Timestamp
    end: pd.Timestamp
    rejected: dict = field(default_factory=dict)


TRADE_COLUMNS = ["symbol", "signal_time", "entry_time", "exit_time", "entry_price", "stop", "qty",
                 "cost", "proceeds", "pnl", "risk_usd", "r_multiple", "return_pct", "exit_reason",
                 "notional_frac"]


class TradeCache:
    """Memoises simulated trades: the same (symbol, bar, stop, exit) is only walked once."""

    def __init__(self):
        self._d: dict = {}

    def get(self, sd: SymbolData, i: int, stop: float, exit_cfg: ExitConfig, costs: CostModel):
        key = (sd.symbol, i, round(float(stop), 12), exit_cfg, costs)
        if key not in self._d:
            self._d[key] = simulate_trade(sd, i, stop, exit_cfg, costs)
        return self._d[key]


def run_portfolio(symbols: dict[str, SymbolData], setups: dict[str, Setup], exit_cfg: ExitConfig,
                  start: pd.Timestamp | None = None, end: pd.Timestamp | None = None,
                  risk: RiskModel = RiskModel(), costs: CostModel = CostModel(),
                  initial_capital: float | None = None, cache: TradeCache | None = None) -> BacktestResult:
    cache = cache or TradeCache()
    capital0 = risk.initial_capital if initial_capital is None else initial_capital
    all_times = np.unique(np.concatenate([sd.times for sd in symbols.values()])) if symbols else np.array([], "int64")
    start_ns = int(pd.Timestamp(start).value) if start is not None else int(all_times[0]) if len(all_times) else 0
    end_ns = int(pd.Timestamp(end).value) if end is not None else int(all_times[-1]) + 1 if len(all_times) else 1

    # 1) candidate entries in time order
    cands = []
    for sym, st in setups.items():
        sd = symbols[sym]
        idx = np.asarray(st.signal_idx, dtype=np.int64)
        ok = idx + 1 < len(sd)
        idx, stops = idx[ok], np.asarray(st.stops, dtype=float)[ok]
        t = sd.times[idx + 1]
        sel = (t >= start_ns) & (t < end_ns)
        cands += zip(t[sel].tolist(), [sym] * int(sel.sum()), idx[sel].tolist(), stops[sel].tolist())
    cands.sort()

    cash = capital0
    fee = costs.fee_rate
    heap: list = []                    # (fill_time, seq, sym)
    open_pos: dict[str, dict] = {}     # sym -> {"tr", "qty", "k" (next fill index)}
    busy_until: dict[str, int] = {}
    records = []
    held: dict[str, np.ndarray] = {}    # sym -> quantity held at each bar's close
    flows = []                          # (time, cash delta)
    rejected = {"busy": 0, "no_cash": 0, "too_small": 0, "invalid": 0}
    seq = 0

    def process_fills_before(t: int):
        nonlocal cash
        while heap and heap[0][0] < t:
            ft, _, sym = heapq.heappop(heap)
            pos = open_pos[sym]
            f = pos["tr"].fills[pos["k"]]
            amount = pos["qty"] * f.frac * f.price * (1 - fee)
            cash += amount
            flows.append((f.time, amount))
            pos["proceeds"] += amount
            pos["k"] += 1
            if pos["k"] < len(pos["tr"].fills):
                heapq.heappush(heap, (pos["tr"].fills[pos["k"]].time, ft, sym))
            else:
                finish(sym, pos)
                del open_pos[sym]

    def finish(sym, pos):
        tr = pos["tr"]
        sd = symbols[sym]
        arr = held.setdefault(sym, np.zeros(len(sd)))
        sold = 0.0
        start_i = tr.entry_idx
        for f in tr.fills:
            stop_i = int(np.searchsorted(sd.times, f.time))  # bar of this fill (value at its close excludes it)
            arr[start_i:stop_i] += pos["qty"] * (1.0 - sold)
            sold += f.frac
            start_i = max(start_i, stop_i)
        pnl = pos["proceeds"] - pos["cost"]
        records.append({
            "symbol": sym, "signal_time": int(symbols[sym].times[tr.signal_idx]), "entry_time": tr.entry_time,
            "exit_time": tr.exit_time, "entry_price": tr.entry_price, "stop": tr.stop, "qty": pos["qty"],
            "cost": pos["cost"], "proceeds": pos["proceeds"], "pnl": pnl, "risk_usd": pos["risk_usd"],
            "r_multiple": pnl / pos["risk_usd"], "return_pct": pnl / pos["cost"],
            "exit_reason": tr.fills[-1].reason if len(tr.fills) == 1 else "+".join(f.reason for f in tr.fills),
            "notional_frac": pos["notional_frac"],
        })

    for t, sym, i, stop in cands:
        process_fills_before(t)
        if busy_until.get(sym, -1) >= t:
            rejected["busy"] += 1
            continue
        sd = symbols[sym]
        tr = cache.get(sd, i, stop, exit_cfg, costs)
        if tr is None:
            rejected["invalid"] += 1
            continue
        tr = truncate_trade(tr, sd, end_ns, costs)
        # mark-to-market equity at the entry moment
        equity = cash
        for osym, pos in open_pos.items():
            osd = symbols[osym]
            j = osd.last_idx_before(t)
            held_frac = 1.0 - sum(f.frac for f in pos["tr"].fills[: pos["k"]])
            equity += pos["qty"] * held_frac * osd.close[max(j, 0)]
        risk_per_unit = tr.entry_price * (1 + fee) - tr.stop * (1 - costs.slippage) * (1 - fee)
        qty = risk.risk_per_trade * equity / risk_per_unit
        notional = qty * tr.entry_price
        max_notional = min(risk.max_position_frac * equity, cash / (1 + fee))
        if notional > max_notional:
            notional = max_notional
            qty = notional / tr.entry_price
        if notional < risk.min_notional:
            rejected["no_cash" if cash / (1 + fee) < risk.min_notional else "too_small"] += 1
            continue
        cost = notional * (1 + fee)
        cash -= cost
        assert cash >= -1e-6, "engine bug: leverage used"
        flows.append((t, -cost))
        open_pos[sym] = {"tr": tr, "qty": qty, "k": 0, "cost": cost, "proceeds": 0.0,
                         "risk_usd": qty * risk_per_unit, "notional_frac": notional / equity}
        busy_until[sym] = tr.exit_time
        seq += 1
        heapq.heappush(heap, (tr.fills[0].time, seq, sym))
    process_fills_before(np.iinfo(np.int64).max)

    trades = pd.DataFrame.from_records(records, columns=TRADE_COLUMNS)
    for col in ("signal_time", "entry_time", "exit_time"):
        trades[col] = pd.to_datetime(trades[col].astype("int64"), utc=True)
    trades = trades.sort_values(["entry_time", "symbol"]).reset_index(drop=True)
    equity = _equity_curve(symbols, held, flows, capital0, all_times, start_ns, end_ns)
    return BacktestResult(trades, equity, capital0, pd.Timestamp(start_ns, tz="UTC"),
                          pd.Timestamp(end_ns, tz="UTC"), rejected)


def _equity_curve(symbols, held, flows, capital0, all_times, start_ns, end_ns) -> pd.Series:
    """Equity at each bar close = cash + market value of open positions."""
    times = all_times[(all_times >= start_ns) & (all_times < end_ns)]
    if len(times) == 0:
        return pd.Series(dtype=float, name="equity")
    tl = pd.DatetimeIndex(pd.to_datetime(times, utc=True))
    cash = pd.Series(capital0, index=tl)
    if flows:
        f = pd.DataFrame(flows, columns=["t", "amt"]).groupby("t")["amt"].sum()
        f.index = pd.to_datetime(f.index.astype("int64"), utc=True)
        cum = f.cumsum()
        cash = capital0 + cum.reindex(tl.union(cum.index)).ffill().fillna(0.0).reindex(tl)
    value = pd.Series(0.0, index=tl)
    for sym, arr in held.items():
        sd = symbols[sym]
        v = pd.Series(arr * sd.close, index=sd.index)
        value = value.add(v.reindex(tl).ffill().fillna(0.0), fill_value=0.0)
    return (cash + value).rename("equity")
