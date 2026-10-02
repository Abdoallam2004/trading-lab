"""In-sample selection, one out-of-sample run, cycle segments, robustness and verdicts."""
from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from lab.config import DATA_DIR
from lab.pit import PointInTimeUniverse

from . import data as d2
from .sim import Prices, metrics, run, utc
from .strategies import BTC, ETH, BuyHold, Context, PlainDCA

IS = ("2018-01-01", "2022-12-31")
OOS = ("2023-01-01", "2026-09-30")
FULL = ("2018-01-01", "2026-09-30")
SEGMENTS = {"2018–19": ("2018-01-01", "2019-12-31"), "2020–21": ("2020-01-01", "2021-12-31"),
            "2022": ("2022-01-01", "2022-12-31"), "2023–24": ("2023-01-01", "2024-12-31"),
            "2025–26": ("2025-01-01", "2026-09-30")}
FRAMES = ("A", "B")
BENCH = {"A": BuyHold, "B": PlainDCA}
MIN_TRADES = 30
ROBUST_FRAC = 0.70
MAX_SEGMENT_SHARE = 0.60


# ----------------------------------------------------------------------------- data
def build_context(data_dir: Path = DATA_DIR, until=None, log=print) -> tuple[Context, Prices]:
    """Load everything. `until` truncates every input (used by the look-ahead test)."""
    cut = (lambda x: x.loc[:utc(until)]) if until is not None else (lambda x: x)
    btc, eth = cut(d2.load_full(BTC, data_dir)), cut(d2.load_full(ETH, data_dir))
    cm = d2.load_coinmetrics()
    cm = cut(cm)
    sig_price = d2.signal_price(btc, cm)
    mvrv = cut(d2.mvrv_inputs(cm, btc))

    uni = json.loads((data_dir / "universe.json").read_text())
    early = {p.stem for p in (d2.EARLY_DIR / "1d").glob("*.parquet")}
    candidates = sorted(set(uni.get("candidates", [])) | early)
    vols, frames = {}, {}
    for s in candidates:
        try:
            for name, seg in d2.load_full_segments(s, data_dir).items():
                seg = cut(seg)
                if len(seg):
                    vols[name] = seg["quote_volume"]
                    frames[name] = seg
        except FileNotFoundError:
            pass
    pit = PointInTimeUniverse(vols, top_n=uni.get("top_n", 50), lookback_months=uni.get("lookback_months", 3))
    end = btc.index[-1]
    used = set()
    for m in pd.date_range(pd.Timestamp("2018-01-01", tz="UTC"), end, freq="MS"):
        used |= set(pit(m))
    used -= {BTC}
    alt_frames = {s: frames[s] for s in sorted(used) if s in frames}
    all_frames = {BTC: btc, ETH: eth, **alt_frames}
    prices = Prices(all_frames)
    alt_close = prices.close[[s for s in alt_frames]]
    log(f"context: BTC {btc.index[0]:%Y-%m-%d}..{end:%Y-%m-%d}, signal history from {sig_price.index[0]:%Y-%m-%d}, "
        f"{len(candidates)} candidate pairs, {len(alt_frames)} alts ever in the point-in-time top 50 since 2018")
    ctx = Context(sig_price, mvrv, alt_close, pit, eth=eth, btc=btc)
    return ctx, prices


# ----------------------------------------------------------------------------- grids
def grid_points(cls) -> list[dict]:
    keys = list(cls.GRID)
    return [dict(zip(keys, combo)) for combo in itertools.product(*cls.GRID.values())]


def neighbours(cls, params: dict) -> list[dict]:
    out = []
    for k, values in cls.GRID.items():
        i = values.index(params[k])
        for j in (i - 1, i + 1):
            if 0 <= j < len(values):
                out.append({**params, k: values[j]})
    return out


def core_pass(m: dict, b: dict, frame: str) -> bool:
    if frame == "A":
        return bool(np.isfinite(m["calmar"]) and m["calmar"] > b["calmar"] and m["max_dd"] <= b["max_dd"])
    better = m["multiple"] > b["multiple"] or m["btc_per_1k"] > b["btc_per_1k"]
    return bool(better and m["max_dd"] <= b["max_dd"])


def is_score(m: dict, frame: str) -> float:
    v = m["calmar"] if frame == "A" else m["multiple"]
    return v if np.isfinite(v) else -np.inf


def segment_shares(res, segments=SEGMENTS) -> dict:
    """Share of total profit made in each cycle segment of one continuous run."""
    eq, fl = res.equity, res.flows
    total = eq.iloc[-1] - res.contributed
    out = {}
    for name, (a, b) in segments.items():
        a, b = pd.Timestamp(a, tz="UTC"), pd.Timestamp(b, tz="UTC")
        before = eq[eq.index < a]
        start_val = before.iloc[-1] if len(before) else 0.0
        inside = eq[(eq.index >= a) & (eq.index <= b)]
        if len(inside) == 0:
            continue
        pnl = inside.iloc[-1] - start_val - fl[(fl.index >= a) & (fl.index <= b)].sum()
        out[name] = pnl / total if total > 0 else np.nan
    return out


# ----------------------------------------------------------------------------- evaluation
@dataclass
class FrameResult:
    frame: str
    chosen: dict
    why: str
    is_: dict
    oos: dict
    full: dict
    segments: dict
    shares: dict
    neighbour_pass: list
    oos_trades: int | None
    label: str = "FAIL"
    reasons: list = field(default_factory=list)


class Evaluator:
    def __init__(self, ctx: Context, prices: Prices, log=print):
        self.ctx, self.prices, self.log = ctx, prices, log
        self._strats: dict = {}
        self._runs: dict = {}

    def strategy(self, cls, params: dict):
        key = (cls, tuple(sorted(params.items())))
        if key not in self._strats:
            self._strats[key] = cls(self.ctx, **params)
        return self._strats[key]

    def run(self, cls, params, period, frame):
        key = (cls, tuple(sorted(params.items())), period, frame)
        if key not in self._runs:
            res = run(self.strategy(cls, params), self.prices, period[0], period[1], frame)
            self._runs[key] = (metrics(res, frame), res)
        return self._runs[key]

    def bench(self, frame, period):
        return self.run(BENCH[frame], {}, period, frame)[0]

    def evaluate(self, cls) -> dict[str, FrameResult]:
        out = {}
        for frame in FRAMES:
            b_is, b_oos = self.bench(frame, IS), self.bench(frame, OOS)
            # 1) choose parameters on in-sample only
            scored = []
            for p in grid_points(cls):
                m = self.run(cls, p, IS, frame)[0]
                scored.append((p, m, m["max_dd"] <= b_is["max_dd"]))
            ok = [x for x in scored if x[2]]
            pool = ok or scored
            p, m_is, _ = max(pool, key=lambda x: is_score(x[1], frame))
            crit = "Calmar" if frame == "A" else "final value ÷ contributed"
            why = (f"best in-sample {crit} among {len(ok)}/{len(scored)} sets with drawdown ≤ benchmark's"
                   if ok else f"no set kept drawdown ≤ benchmark's in-sample; best in-sample {crit}")
            # 2) one out-of-sample run with the chosen set
            m_oos, res_oos = self.run(cls, p, OOS, frame)
            m_full, res_full = self.run(cls, p, FULL, frame)
            segs = {k: self.run(cls, p, v, frame)[0] for k, v in SEGMENTS.items()}
            nb = [(q, core_pass(self.run(cls, q, OOS, frame)[0], b_oos, frame)) for q in neighbours(cls, p)]
            n_trades = len(res_oos.trades) if cls.key == "S7" else None
            fr = FrameResult(frame, p, why, m_is, m_oos, m_full, segs, segment_shares(res_full), nb, n_trades)
            judge(fr, b_oos)
            out[frame] = fr
            self.log(f"  {cls.key:<5} frame {frame}: {fr.label:<12} chosen {p}")
        return out


def judge(fr: FrameResult, b_oos: dict) -> None:
    reasons = []
    core = core_pass(fr.oos, b_oos, fr.frame)
    if fr.frame == "A":
        reasons.append(f"OOS Calmar {fr.oos['calmar']:.2f} vs B1 {b_oos['calmar']:.2f}; "
                       f"max DD {fr.oos['max_dd']:.1%} vs {b_oos['max_dd']:.1%}")
    else:
        reasons.append(f"OOS value÷contributed {fr.oos['multiple']:.2f} vs B2 {b_oos['multiple']:.2f}; "
                       f"BTC per $1k {fr.oos['btc_per_1k']:.4f} vs {b_oos['btc_per_1k']:.4f}; "
                       f"max DD {fr.oos['max_dd']:.1%} vs {b_oos['max_dd']:.1%}")
    nb_frac = np.mean([ok for _, ok in fr.neighbour_pass]) if fr.neighbour_pass else np.nan
    robust = bool(np.isfinite(nb_frac) and nb_frac >= ROBUST_FRAC)
    shares = [v for v in fr.shares.values() if np.isfinite(v)]
    conc_ok = bool(shares) and max(shares) <= MAX_SEGMENT_SHARE
    if fr.oos_trades is not None and fr.oos_trades < MIN_TRADES:
        fr.label = "INCONCLUSIVE"
        reasons.append(f"insufficient data: {fr.oos_trades} OOS trades (< {MIN_TRADES})")
    elif not core:
        fr.label = "FAIL"
    else:
        fr.label = "PASS" if robust and conc_ok else "INCONCLUSIVE"
    if core:
        reasons.append(f"neighbours passing: {nb_frac:.0%} (need ≥ {ROBUST_FRAC:.0%})" if np.isfinite(nb_frac)
                       else "no neighbouring parameter sets")
        reasons.append("profit concentration OK" if conc_ok else
                       f"largest cycle share of full-period profit {max(shares) if shares else float('nan'):.0%} "
                       f"(> {MAX_SEGMENT_SHARE:.0%} or no profit)")
    fr.reasons = reasons


def lookahead_check(items, cutoffs, data_dir: Path = DATA_DIR, frames=FRAMES) -> list[dict]:
    """Real-data version of the unit test: for each cutoff t, rebuild ALL inputs from data
    ending at t and at t + 1 bar, run each (strategy, params) from 2018 to t, and require
    identical daily equity. `items` = [(cls, params), ...]."""
    rows = []
    for t in cutoffs:
        t = utc(t)
        ctxs = [build_context(data_dir, until=u, log=lambda *_: None) for u in (t, t + pd.Timedelta(days=1))]
        for cls, params in items:
            for frame in frames:
                a, b = (run(cls(c, **params), p, FULL[0], t, frame).equity for c, p in ctxs)
                diff = float((a - b.reindex(a.index)).abs().max())
                rows.append({"strategy": cls.key, "params": params, "frame": frame, "cutoff": f"{t:%Y-%m-%d}",
                             "max_abs_diff": diff, "ok": bool(diff < 1e-6)})
    return rows
