"""Single-asset trade engine for Part B (spot, long-only, one position at a time).

Orders are produced by setups from information up to the close of their signal bar and
can only fill from the next bar on. Fills:
  * market: the open of `valid_from`;
  * limit:  the first bar in [start, valid_to] whose low reaches the limit, at min(open, limit);
            optionally cancelled first if a bar closes below `cancel_below`.
Exits (scanned forward, vectorised in growing chunks):
  * stop:   low <= stop  -> min(open, stop) (exactly the stop on the entry bar);
  * target: high >= target -> max(open, target) (not on a limit-fill bar: order unknown);
  * time:   close of bar entry + cap.
When a bar touches both stop and target, the stop is assumed first.
Costs: fee + slippage on every fill. Sizing: lose 1.5% of equity at the stop, capped by cash.
At most `max_per_day` new entries per UTC day.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

RISK = 0.015


@dataclass(frozen=True)
class Costs:
    fee: float = 0.001
    slip: float = 0.0005

    def doubled(self) -> "Costs":
        return Costs(self.fee * 2, self.slip * 2)


@dataclass
class Order:
    sig_idx: int                  # bar whose close produced the signal
    valid_from: int               # first bar that may fill
    valid_to: int                 # last bar that may fill (== valid_from for market orders)
    kind: str = "market"          # market | limit
    limit: float = np.nan
    stop: float = np.nan          # absolute stop, or ...
    stop_offset: float = np.nan   # ... stop = fill - offset
    target: float = np.nan        # absolute target, or ...
    target_r: float = np.nan      # ... target = fill + r * (fill - stop)
    cap: int | None = None        # max bars held after the entry bar
    cancel_below: float = np.nan  # limit cancelled if a close falls below this before the fill
    atr: float = np.nan           # ATR at the signal (for the random baseline)


TRADE_COLS = ["sig_time", "entry_time", "exit_time", "entry", "exit", "stop", "target", "r", "ret",
              "bars", "reason", "atr", "stop_atr", "target_atr", "cap", "entry_idx"]


class Bars:
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.index = df.index.as_unit("ns")
        self.o = df["open"].to_numpy(float)
        self.h = df["high"].to_numpy(float)
        self.l = df["low"].to_numpy(float)
        self.c = df["close"].to_numpy(float)
        self.day = self.index.normalize().asi8 if len(df) else np.array([], "int64")

    def __len__(self):
        return len(self.o)


def _first_true(mask: np.ndarray) -> int:
    return int(np.argmax(mask)) if mask.any() else -1


def scan_exit(b: Bars, j: int, stop: float, tgt: float, cap: int | None, limit_fill: bool):
    """Return (exit_bar, exit_price, reason) for a position entered on bar j."""
    n = len(b)
    end = n - 1 if cap is None else min(n - 1, j + cap)
    k0, chunk = j, 64
    has_t = np.isfinite(tgt)
    while k0 <= end:
        k1 = min(end, k0 + chunk - 1)
        hs = b.l[k0:k1 + 1] <= stop
        ht = b.h[k0:k1 + 1] >= tgt if has_t else np.zeros(k1 - k0 + 1, bool)
        if k0 == j and limit_fill:
            ht[0] = False
        i_s, i_t = _first_true(hs), _first_true(ht)
        if i_s >= 0 or i_t >= 0:
            if i_s >= 0 and (i_t < 0 or i_s <= i_t):
                k = k0 + i_s
                return k, (stop if k == j else min(b.o[k], stop)), "stop"
            k = k0 + i_t
            return k, (tgt if k == j else max(b.o[k], tgt)), "target"
        k0, chunk = k1 + 1, chunk * 2
    return end, b.c[end], ("time" if cap is not None and end == j + cap else "end")


def _limit_fill(b: Bars, a: int, z: int, price: float, cancel_below: float) -> int:
    if a > z:
        return -1
    fill = b.l[a:z + 1] <= price
    i_f = _first_true(fill)
    if np.isfinite(cancel_below):
        i_c = _first_true(b.c[a:z + 1] < cancel_below)
        if i_c >= 0 and (i_f < 0 or i_c < i_f):
            return -1
    return a + i_f if i_f >= 0 else -1


def simulate(b: Bars, orders: list[Order], costs: Costs = Costs(), max_per_day: int = 3,
             start=None, end=None) -> pd.DataFrame:
    """Run orders in time order, one position at a time. Entries must fall in [start, end]."""
    orders = sorted(orders, key=lambda o: (o.valid_from, o.sig_idx))
    lo = int(np.searchsorted(b.index.asi8, pd.Timestamp(start).value)) if start is not None else 0
    hi = int(np.searchsorted(b.index.asi8, pd.Timestamp(end).value, side="right")) - 1 if end is not None else len(b) - 1
    free_from, per_day, rows = lo, {}, []
    fee, slip = costs.fee, costs.slip
    for od in orders:
        if od.valid_from >= len(b) or od.valid_from > hi:
            continue
        a = max(od.valid_from, free_from)
        if od.kind == "market":
            if a != od.valid_from:
                continue
            j, fill = a, b.o[a]
        else:
            j = _limit_fill(b, a, min(od.valid_to, hi), od.limit, od.cancel_below)
            if j < 0:
                continue
            fill = min(b.o[j], od.limit)
        if j > hi or per_day.get(b.day[j], 0) >= max_per_day:
            continue
        stop = fill - od.stop_offset if np.isfinite(od.stop_offset) else od.stop
        if not (np.isfinite(stop) and stop < fill):
            continue
        tgt = fill + od.target_r * (fill - stop) if np.isfinite(od.target_r) else od.target
        if np.isfinite(tgt) and tgt <= fill:
            continue
        e_cost = fill * (1 + slip) * (1 + fee)
        r_unit = e_cost - stop * (1 - slip) * (1 - fee)
        k, px, why = scan_exit(b, j, stop, tgt, od.cap, od.kind == "limit")
        x_net = px * (1 - slip) * (1 - fee)
        frac = min(1.0, RISK * e_cost / r_unit)  # fraction of equity put in the trade
        per_day[b.day[j]] = per_day.get(b.day[j], 0) + 1
        free_from = k + 1
        atr = od.atr
        rows.append((b.index[od.sig_idx], b.index[j], b.index[k], fill, px, stop, tgt,
                     (x_net - e_cost) / r_unit, frac * (x_net / e_cost - 1), k - j + 1, why, atr,
                     (fill - stop) / atr if atr > 0 else np.nan,
                     (tgt - fill) / atr if atr > 0 and np.isfinite(tgt) else np.nan, od.cap, j))
    return pd.DataFrame(rows, columns=TRADE_COLS)
