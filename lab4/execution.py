"""Lab 4 shared execution model: limit-order ladders, partial exits, cost scenarios, fill models.

Cost scenarios (per fill):
  C0  Lab 3: 0.10% fee + 0.05% slippage on EVERY fill (limits included)
  C1  user:  0.075% fee (BNB discount), no slippage on limit fills, stops filled at the stop
  C2  C1 + stops are stop-market orders: 0.05% slippage; a bar that opens through the stop fills at the open
Fill models for limits: "through" (verdicts) = the bar must trade >= 0.02% beyond the limit;
"touch" = touching the limit is enough (comparison only). No partial fills or queue model.
Entry modes: E1 one limit at the anchor; E2 three limits 0.09% apart; E3 three limits 0.25 ATR apart.
Exit modes:  X1 the setup's own single target; X2 thirds at 1R/2R/3R; X3 = X2 + stop to breakeven after
             the first third. Stops: S-a 0.1% below the reference low; S-b reference low - 0.5 ATR.
Sizing: if every entry level fills and the stop is hit, the loss is 1.5% of equity (capped by cash).
R = P&L / that planned risk, so a partly filled ladder risks (and earns) less than 1R.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from lab3.engine import Bars

RISK = 0.015
THROUGH = 0.0002


@dataclass(frozen=True)
class Scenario:
    name: str
    fee: float
    limit_slip: float
    stop_slip: float


C0 = Scenario("C0", 0.001, 0.0005, 0.0005)
C1 = Scenario("C1", 0.00075, 0.0, 0.0)
C2 = Scenario("C2", 0.00075, 0.0, 0.0005)
SCENARIOS = {"C0": C0, "C1": C1, "C2": C2}


@dataclass(frozen=True)
class Exec:
    entry: str = "E1"   # E1 | E2 | E3
    exit: str = "X1"    # X1 | X2 | X3
    stop: str = "S-b"   # S-a | S-b

    @property
    def label(self) -> str:
        return f"{self.entry}/{self.exit}/{self.stop}"


EXEC_GRID = [Exec(e, x, s) for e in ("E1", "E2", "E3") for x in ("X1", "X2", "X3") for s in ("S-a", "S-b")]


@dataclass
class Signal:
    sig_idx: int
    valid_from: int
    valid_to: int
    anchor: float            # first entry limit
    ref_low: float           # structural low the stop hangs below
    atr: float
    target: float = np.nan   # setup's own absolute target (X1), or ...
    target_r: float = np.nan  # ... a multiple of R (X1)
    cap: int | None = None
    cancel_below: float = np.nan


COLS = ["sig_time", "entry_time", "exit_time", "entry", "exit", "stop", "r", "ret", "bars", "reason", "fills",
        "atr", "stop_atr", "target_atr", "cap", "entry_idx"]


def _first(mask):
    return int(np.argmax(mask)) if mask.any() else -1


def _next_event(b: Bars, a: int, z: int, stop: float, tgt: float):
    """First bar in [a, z] where low <= stop or high >= tgt (np.inf = none)."""
    k0, chunk = a, 64
    while k0 <= z:
        k1 = min(z, k0 + chunk - 1)
        m = (b.l[k0:k1 + 1] <= stop) | (b.h[k0:k1 + 1] >= tgt)
        i = _first(m)
        if i >= 0:
            return k0 + i
        k0, chunk = k1 + 1, chunk * 2
    return -1


class _Trade:
    """State of one position: entry ladder, partial exits, current stop."""

    def __init__(self, sg: Signal, ex: Exec, sc: Scenario, tt: float):
        self.sg, self.ex, self.sc, self.tt = sg, ex, sc, tt
        atr = sg.atr
        self.stop = sg.ref_low * (1 - 0.001) if ex.stop == "S-a" else sg.ref_low - 0.5 * atr
        if ex.entry == "E1":
            lv = [sg.anchor]
        elif ex.entry == "E2":
            lv = [sg.anchor, sg.anchor * (1 - 0.0009), sg.anchor * (1 - 0.0018)]
        else:
            lv = [sg.anchor, sg.anchor - 0.25 * atr, sg.anchor - 0.5 * atr]
        self.levels = [L for L in lv if L > self.stop] if np.isfinite(self.stop) and self.stop > 0 else []
        self.ok = bool(self.levels)
        if not self.ok:
            return
        fee = sc.fee
        self.avg = float(np.mean(self.levels))
        self.unit_risk = self.avg * (1 + fee) - self.stop * (1 - sc.stop_slip) * (1 - fee)
        self.qty_tot = min(RISK / self.unit_risk, 1.0 / (self.avg * (1 + fee)))   # per $1 of equity
        self.q_lvl = self.qty_tot / len(self.levels)
        rd = self.avg - self.stop
        if ex.exit == "X1":
            t1 = sg.target if np.isfinite(sg.target) else self.avg + sg.target_r * rd
            self.ok = bool(t1 > self.avg)
            self.targets = [(t1, 1.0)]
        else:
            self.targets = [(self.avg + k * rd, 1 / 3) for k in (1, 2, 3)]
        self.first_target = self.targets[0][0]
        self.filled = [False] * len(self.levels)
        self.held = self.cost = self.proceeds = 0.0
        self.first = None
        self.cur_stop = self.stop
        self.exit_bar = self.exit_px = None
        self.why = "end"

    def fill(self, b: Bars, j: int) -> bool:
        new = False
        for i, L in enumerate(self.levels):
            if not self.filled[i] and b.l[j] <= L * (1 - self.tt):
                px = min(b.o[j], L) * (1 + self.sc.limit_slip)
                self.filled[i] = new = True
                self.held += self.q_lvl
                self.cost += self.q_lvl * px * (1 + self.sc.fee)
                self.first = j if self.first is None else self.first
        return new

    def _sell(self, q, px, j, why):
        self.proceeds += q * px * (1 - self.sc.fee)
        self.held -= q
        if self.held <= 1e-15:
            self.held = 0.0
            self.exit_bar, self.exit_px, self.why = j, px, why
            return True
        return False

    def exits(self, b: Bars, k: int, fill_bar: bool) -> bool:
        """Process stop / targets / time on bar k (stop first). Returns True when flat."""
        sc = self.sc
        if b.l[k] <= self.cur_stop:
            px = (self.cur_stop if fill_bar else min(b.o[k], self.cur_stop)) * (1 - sc.stop_slip)
            return self._sell(self.held, px, k, "stop" if self.cur_stop < self.avg else "breakeven")
        if not fill_bar:
            for t in [t for t in self.targets if b.h[k] >= t[0] * (1 + self.tt)]:
                last = t is self.targets[-1]
                q = self.held if last else min(self.held, self.qty_tot * t[1])
                self.targets.remove(t)
                if self.ex.exit == "X3":
                    self.cur_stop = max(self.cur_stop, self.avg)
                if self._sell(q, max(b.o[k], t[0]) * (1 - sc.limit_slip), k, "target"):
                    return True
            if not self.targets and self.held > 0:
                return self._sell(self.held, b.c[k] * (1 - sc.limit_slip), k, "target")
        cap = self.sg.cap
        if cap is not None and self.first is not None and k - self.first >= cap:
            return self._sell(self.held, b.c[k] * (1 - sc.limit_slip), k, "time")
        return False


def run_trade(b: Bars, sg: Signal, ex: Exec, sc: Scenario, tt: float, n: int, per_day=None, max_per_day=3):
    """Simulate one signal. Returns the finished _Trade, or None (no fill / invalid / daily cap)."""
    tr = _Trade(sg, ex, sc, tt)
    if not tr.ok:
        return None
    last_entry = min(sg.valid_to, n - 1)
    j, done = sg.valid_from, False
    while j < n and not done:
        if j <= last_entry and not all(tr.filled):
            if tr.first is None and np.isfinite(sg.cancel_below) and j > sg.valid_from \
                    and b.c[j - 1] < sg.cancel_below:
                return None   # zone broken before any fill
            new = tr.fill(b, j)
            if tr.first is None:
                j += 1
                continue
            if new and tr.first == j and per_day is not None and per_day.get(b.day[j], 0) >= max_per_day:
                return None
            done = tr.exits(b, j, fill_bar=new)
            j += 1
            continue
        if tr.first is None:
            return None
        z = n - 1 if sg.cap is None else min(n - 1, tr.first + sg.cap)
        nxt = tr.targets[0][0] * (1 + tt) if tr.targets else np.inf
        k = _next_event(b, j, z, tr.cur_stop, nxt)
        if k < 0:
            why = "time" if sg.cap is not None and z == tr.first + sg.cap else "end"
            tr._sell(tr.held, b.c[z] * (1 - sc.limit_slip), z, why)
            return tr
        done = tr.exits(b, k, fill_bar=False)
        j = k + 1
    if tr.first is None:
        return None
    if not done:   # data ended with the position open
        tr._sell(tr.held, b.c[n - 1], n - 1, "end")
    return tr


def trade_r(tr) -> float:
    return (tr.proceeds - tr.cost) / (tr.qty_tot * tr.unit_risk)


def simulate(b: Bars, signals: list[Signal], ex: Exec, sc: Scenario, fill: str = "through",
             max_per_day: int = 3, end_idx: int | None = None) -> pd.DataFrame:
    """Run signals in time order, one position at a time (see module docstring)."""
    tt = THROUGH if fill == "through" else 0.0
    n = len(b) if end_idx is None else min(len(b), end_idx + 1)
    rows, free_from, per_day = [], 0, {}
    for sg in sorted(signals, key=lambda s: (s.valid_from, s.sig_idx)):
        if sg.valid_from >= n or sg.valid_from < free_from:
            continue
        tr = run_trade(b, sg, ex, sc, tt, n, per_day, max_per_day)
        if tr is None:
            continue
        per_day[b.day[tr.first]] = per_day.get(b.day[tr.first], 0) + 1
        free_from = tr.exit_bar + 1
        pnl = tr.proceeds - tr.cost
        atr = sg.atr
        rows.append((b.index[sg.sig_idx], b.index[tr.first], b.index[tr.exit_bar], tr.avg, tr.exit_px, tr.stop,
                     trade_r(tr), pnl, tr.exit_bar - tr.first + 1, tr.why, int(sum(tr.filled)), atr,
                     (tr.avg - tr.stop) / atr if atr > 0 else np.nan,
                     (tr.first_target - tr.avg) / atr if atr > 0 else np.nan, sg.cap, tr.first))
    return pd.DataFrame(rows, columns=COLS)
