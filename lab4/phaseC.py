"""Phase C: derivatives and flow data as SPOT signals — event studies.

Every signal fires at the timestamp it becomes known (daily inputs: the end of day D = D+1 00:00 UTC;
4-hour inputs: the bar's close). Forward spot return over h days = close of the 1h bar ending at
T + h days / open of the first 1h bar starting at or after T, minus 1.
Thresholds are expanding-window percentiles (>= 180 observations), never fixed numbers.
Events are de-clustered: a new event needs the condition to switch on again and >= 7 days since
the last one.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from lab3.partA import expanding_percentile

from .data import load

HORIZONS = (1, 3, 7, 30)
MIN_EVENTS = 10   # fewer events: no test (a bootstrap over 4 events is degenerate)
MIN_OBS = 180
GAP_DAYS = 7
SIGNALS = {   # name: (description, expected sign of the forward excess return)
    "D1": ("crowded shorts: 3-day mean funding < 10th pct while BTC > 200d SMA (buy)", +1),
    "D2": ("overheated longs: daily funding > 95th pct AND open interest at a 90-day high (reduce)", -1),
    "D3": ("flush: 4h OI drop <= 5th pct with a >= 2 ATR price drop, then a close back above the pre-flush low", +1),
    "D4": ("absorption: price makes a 20-day lower low while cumulative spot taker delta makes a higher low", +1),
    "D5": ("discount basis: perp premium index < 5th pct", +1),
    "D6a": ("crowd short: global long/short account ratio < 10th pct (contrarian buy)", +1),
    "D6b": ("crowd long: global long/short account ratio > 90th pct (contrarian reduce)", -1),
}


# ----------------------------------------------------------------------------- inputs
def daily_inputs(asset: str, btc_daily: pd.DataFrame) -> pd.DataFrame:
    """One row per UTC day D with values known at the END of D (index = D)."""
    spot = load(f"spot_{asset}_1d")
    d = pd.DataFrame(index=spot.index)
    d["open"], d["high"], d["low"], d["close"] = spot["open"], spot["high"], spot["low"], spot["close"]
    d["delta"] = 2 * spot["taker_buy_quote"] - spot["quote_volume"]      # taker buys - taker sells (USDT)
    d["cvd"] = d["delta"].cumsum()
    known = d.index + pd.Timedelta(days=1)                               # end of day D

    f = load(f"funding_{asset}")["funding"]
    f3 = f.rolling("3D").mean()                                          # mean of the last 3 days' fundings
    fd = f.rolling("1D").mean()
    d["funding3"] = _asof(f3, known)
    d["funding1"] = _asof(fd, known)
    try:
        mt = load(f"metrics_{asset}")
        d["oi"] = _asof(mt["sum_open_interest_value"].dropna(), known)
        d["ls_ratio"] = _asof(mt["count_long_short_ratio"].dropna(), known)
        pos = mt.index.searchsorted(known, side="right") - 1
        last_seen = mt.index[np.clip(pos, 0, None)]
        old = (pos < 0) | ((known - last_seen) > pd.Timedelta(hours=6))
        d.loc[np.asarray(old), ["oi", "ls_ratio"]] = np.nan                # no metrics yet / outage
    except FileNotFoundError:
        d["oi"] = d["ls_ratio"] = np.nan
    prem = load(f"premium_{asset}_1d")["close"]
    prem.index = prem.index + pd.Timedelta(days=1)                       # known at the daily close
    d["premium"] = _asof(prem, known)
    sma = btc_daily["close"].rolling(200, min_periods=200).mean()
    d["btc_up"] = (btc_daily["close"] > sma).reindex(d.index).fillna(False).astype(bool)
    slope = (sma / sma.shift(20) - 1).reindex(d.index)
    d["regime3"] = np.select([slope > 0.02, slope < -0.02], ["bull", "bear"], "range")
    d.loc[slope.isna().to_numpy(), "regime3"] = "none"
    d["regime2"] = np.where(d["btc_up"], "BTC>200D", "BTC<200D")
    return d


def _asof(s: pd.Series, when: pd.DatetimeIndex) -> np.ndarray:
    s = s.dropna().sort_index()
    pos = s.index.searchsorted(when, side="right") - 1
    vals = s.to_numpy()
    out = np.where(pos >= 0, vals[np.clip(pos, 0, None)], np.nan)
    return out


def onsets(cond: pd.Series, gap_days: int = GAP_DAYS) -> pd.DatetimeIndex:
    cond = cond.fillna(False).astype(bool)
    start = cond & ~cond.shift(1, fill_value=False)
    out, last = [], None
    for t in cond.index[start.to_numpy()]:
        if last is None or (t - last) >= pd.Timedelta(days=gap_days):
            out.append(t)
            last = t
    return pd.DatetimeIndex(out, tz="UTC") if not out else pd.DatetimeIndex(out).tz_convert("UTC")


def daily_signals(d: pd.DataFrame) -> dict[str, pd.DatetimeIndex]:
    """Signal days D (the event becomes known at D+1 00:00)."""
    pct = {c: expanding_percentile(d[c], MIN_OBS) for c in ("funding3", "funding1", "premium", "ls_ratio")}
    oi_high = d["oi"] >= d["oi"].rolling(90, min_periods=90).max()
    low20 = d["low"].shift(1).rolling(20, min_periods=20).min()
    cvd_low20 = d["cvd"].shift(1).rolling(20, min_periods=20).min()
    out = {
        "D1": onsets((pct["funding3"] < 10) & d["btc_up"]),
        "D2": onsets((pct["funding1"] > 95) & oi_high),
        "D4": onsets((d["low"] < low20) & (d["cvd"] > cvd_low20)),
        "D5": onsets(pct["premium"] < 5),
        "D6a": onsets(pct["ls_ratio"] < 10),
        "D6b": onsets(pct["ls_ratio"] > 90),
    }
    return out


def flush_events(asset: str) -> pd.DatetimeIndex:
    """D3 on 4h bars. Returns event times = the close of the reclaim bar."""
    from lab.indicators import atr as wilder_atr
    s = load(f"spot_{asset}_4h")
    try:
        mt = load(f"metrics_{asset}")["sum_open_interest_value"].dropna()
    except FileNotFoundError:
        return pd.DatetimeIndex([], tz="UTC")
    close_t = s.index + pd.Timedelta(hours=4)
    oi = pd.Series(_asof(mt, close_t), index=s.index)
    oi_chg = oi.pct_change(fill_method=None)
    q = expanding_percentile(oi_chg, MIN_OBS)
    a = wilder_atr(s, 14)
    drop = s["close"] <= s["close"].shift(3) - 2 * a.shift(3)
    pre_low = s["low"].shift(4).rolling(20, min_periods=20).min()
    flush = (q <= 5) & drop
    c, l = s["close"].to_numpy(), s["low"].to_numpy()
    ev, last = [], None
    for i in np.flatnonzero(flush.to_numpy()):
        lvl = pre_low.iloc[i]
        if not np.isfinite(lvl) or l[max(0, i - 3):i + 1].min() > lvl:
            continue   # the flush did not take out the pre-flush low
        for r in range(i + 1, min(i + 13, len(s))):
            if c[r] > lvl:
                t = close_t[r]
                if last is None or t - last >= pd.Timedelta(days=GAP_DAYS):
                    ev.append(t)
                    last = t
                break
    return pd.DatetimeIndex(ev, tz="UTC") if not ev else pd.DatetimeIndex(ev).tz_convert("UTC")


# ----------------------------------------------------------------------------- forward returns
class Forward:
    def __init__(self, asset: str):
        h = load(f"spot_{asset}_1h")
        self.t_open = h.index
        self.o = h["open"].to_numpy()
        self.c = h["close"].to_numpy()
        self.t_close = h.index + pd.Timedelta(hours=1)

    def ret(self, times: pd.DatetimeIndex, days: int) -> np.ndarray:
        i = self.t_open.searchsorted(times, side="left")
        j = self.t_close.searchsorted(times + pd.Timedelta(days=days), side="right") - 1
        ok = (i < len(self.o)) & (j < len(self.c)) & (j > i) & (self.t_close[np.clip(j, 0, len(self.c) - 1)]
                                                                 >= times + pd.Timedelta(days=days) - pd.Timedelta(hours=1))
        out = np.full(len(times), np.nan)
        out[ok] = self.c[j[ok]] / self.o[i[ok]] - 1
        return out


def block_bootstrap_mean(x: np.ndarray, block: int, n: int = 5000, seed: int = 3) -> np.ndarray:
    x = x[np.isfinite(x)]
    if len(x) < 3:
        return np.array([])
    rng = np.random.default_rng(seed)
    nb = math.ceil(len(x) / block)
    starts = rng.integers(0, len(x), size=(n, nb))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % len(x)
    return x[idx.reshape(n, -1)[:, :len(x)]].mean(axis=1)


def benjamini_hochberg(p: np.ndarray, q: float = 0.10) -> np.ndarray:
    p = np.asarray(p, float)
    ok = np.isfinite(p)
    out = np.zeros(len(p), bool)
    ps = p[ok]
    if len(ps) == 0:
        return out
    order = np.argsort(ps)
    m = len(ps)
    thresh = q * (np.arange(1, m + 1) / m)
    passed = ps[order] <= thresh
    k = np.max(np.flatnonzero(passed)) + 1 if passed.any() else 0
    sel = np.zeros(m, bool)
    sel[order[:k]] = True
    out[np.flatnonzero(ok)] = sel
    return out


def event_study(asset: str, btc_daily: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Rows per (signal, horizon): events, mean excess vs same-regime unconditional, CI, p, by regime."""
    d = daily_inputs(asset, btc_daily)
    sig = daily_signals(d)
    sig["D3"] = flush_events(asset)
    fw = Forward(asset)
    day_known = d.index + pd.Timedelta(days=1)
    rows = []
    for name, times in sig.items():
        is_daily = name != "D3"
        ev_known = (times + pd.Timedelta(days=1)) if is_daily else times
        ev_day = times if is_daily else (times - pd.Timedelta(seconds=1)).normalize()
        reg2 = d["regime2"].reindex(ev_day).to_numpy()
        reg3 = d["regime3"].reindex(ev_day).to_numpy()
        # signal coverage window (unconditional baseline uses the same span)
        lo, hi = (ev_day.min(), ev_day.max()) if len(ev_day) else (None, None)
        for h in HORIZONS:
            ev = fw.ret(ev_known, h)
            allr = pd.Series(fw.ret(day_known, h), index=d.index)
            span = allr[(allr.index >= lo) & (allr.index <= hi)] if lo is not None else allr.iloc[:0]
            base = span.groupby(d["regime2"].reindex(span.index)).mean()
            excess = ev - pd.Series(reg2).map(base).to_numpy()
            ok = np.isfinite(excess)
            block = max(1, min(math.ceil(h / GAP_DAYS), int(ok.sum()) // 3))
            boot = block_bootstrap_mean(excess[ok], block=block) if ok.sum() >= MIN_EVENTS else np.array([])
            mean = float(np.nanmean(excess)) if ok.any() else np.nan
            p = (2 * min((boot <= 0).mean(), (boot >= 0).mean())) if len(boot) else np.nan
            by3 = {}
            for r in ("bull", "bear", "range"):
                m = ok & (reg3 == r)
                by3[r] = (int(m.sum()), float(np.mean(excess[m])) if m.sum() else np.nan)
            rows.append({"asset": asset, "signal": name, "horizon": h, "events": int(ok.sum()),
                         "mean_fwd": float(np.nanmean(ev)) if ok.any() else np.nan, "mean_excess": mean,
                         "ci_lo": float(np.percentile(boot, 2.5)) if len(boot) else np.nan,
                         "ci_hi": float(np.percentile(boot, 97.5)) if len(boot) else np.nan, "p": p,
                         "first": lo, "last": hi,
                         **{f"{r}_n": v[0] for r, v in by3.items()}, **{f"{r}_excess": v[1] for r, v in by3.items()}})
    return pd.DataFrame(rows), sig


def judge(btc: pd.DataFrame, eth: pd.DataFrame, q: float = 0.10) -> pd.DataFrame:
    """FDR across all BTC tests, then ETH sign and >= 2 of 3 regime consistency."""
    t = btc.copy()
    t["fdr_pass"] = benjamini_hochberg(t["p"].to_numpy(), q)
    t["expected_sign"] = t["signal"].map(lambda s: SIGNALS[s][1])
    t["right_sign"] = np.sign(t["mean_excess"]) == t["expected_sign"]
    e = eth.set_index(["signal", "horizon"])["mean_excess"]
    t["eth_excess"] = [e.get((s, h), np.nan) for s, h in zip(t["signal"], t["horizon"])]
    t["eth_same_sign"] = np.sign(t["eth_excess"]) == np.sign(t["mean_excess"])
    reg_ok = []
    for _, r in t.iterrows():
        k = sum(1 for g in ("bull", "bear", "range")
                if r[f"{g}_n"] >= 5 and np.sign(r[f"{g}_excess"]) == np.sign(r["mean_excess"]))
        reg_ok.append(k)
    t["regimes_same_sign"] = reg_ok
    t["survives"] = t["fdr_pass"] & t["right_sign"] & t["eth_same_sign"] & (t["regimes_same_sign"] >= 2)
    return t
