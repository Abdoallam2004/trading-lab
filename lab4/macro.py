"""Phase D: macro correlations, macro regimes and a macro size overlay — with what is reachable.

Available: VIX daily (CBOE via DataHub, known the next UTC day), dollar proxy = 1 / EUR/USDT and gold
proxy = PAXG/USDT (Binance daily), US 10y MONTHLY. Not available here: Nasdaq-100, DXY itself, daily
10y, Fed balance sheet, FOMC/CPI calendars (see reports/lab4_data_inventory.md).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from lab2 import signals as sg
from lab2.strategies import BTC, S2_TABLES, DCA200W, RegimeFilter, Strategy
from lab3.partA import expanding_percentile

from .data import load, vix_known
from .phaseC import block_bootstrap_mean


def daily_returns() -> pd.DataFrame:
    """Same-calendar-date daily returns (descriptive correlations only, not signals)."""
    btc = load("spot_BTCUSDT_1d")["close"]
    eur = load("spot_EURUSDT_1d")["close"]
    paxg = load("spot_PAXGUSDT_1d")["close"]
    vix = load("vix")["close"]
    vix.index = vix.index.normalize()
    df = pd.DataFrame({"BTC": btc.pct_change(fill_method=None),
                       "dollar_proxy": (1 / eur).pct_change(fill_method=None),
                       "gold_proxy": paxg.pct_change(fill_method=None)})
    df["VIX_change"] = vix.pct_change(fill_method=None).reindex(df.index)   # weekdays only
    return df


def rolling_corr(df: pd.DataFrame, window: int = 90) -> pd.DataFrame:
    out = {}
    for c in df.columns.drop("BTC"):
        pair = df[["BTC", c]].dropna()
        out[c] = pair["BTC"].rolling(window, min_periods=int(window * 0.6)).corr(pair[c])
    return pd.DataFrame(out)


def instability(rc: pd.DataFrame) -> pd.DataFrame:
    rows = {}
    for c in rc:
        s = rc[c].dropna()
        rows[c] = {"first": s.index[0].date(), "mean": s.mean(), "std": s.std(), "min": s.min(), "max": s.max(),
                   "share_positive": (s > 0).mean(), "sign_flips": int((np.sign(s).diff().abs() > 0).sum())}
    return pd.DataFrame(rows).T


def monthly_10y_corr() -> dict:
    y = load("us10y_monthly").iloc[:, 0]
    btc = load("spot_BTCUSDT_1d")["close"].resample("MS").last()
    df = pd.DataFrame({"btc": btc.pct_change(fill_method=None),
                       "dy": y.reindex(btc.index, method="ffill").diff()}).dropna()
    rc = df["btc"].rolling(24, min_periods=18).corr(df["dy"]).dropna()
    return {"months": len(df), "full_corr": float(df.corr().iloc[0, 1]), "rolling24_min": float(rc.min()),
            "rolling24_max": float(rc.max())}


def macro_regime() -> pd.DataFrame:
    """Day D (known at its end): risk-on = dollar proxy down over 20 days AND VIX below its 200-day SMA."""
    btc = load("spot_BTCUSDT_1d")
    known = btc.index + pd.Timedelta(days=1)
    eur = load("spot_EURUSDT_1d")["close"]
    eur_k = eur.copy()
    eur_k.index = eur.index + pd.Timedelta(days=1)
    vk = vix_known()
    vsma = vk.rolling(200, min_periods=200).mean()
    df = pd.DataFrame(index=btc.index)
    df["eur"] = _asof(eur_k, known)
    df["eur_20"] = _asof(eur_k.shift(20), known)
    df["vix"] = _asof(vk, known)
    df["vix_sma"] = _asof(vsma, known)
    dollar_down = df["eur"] > df["eur_20"]
    df["risk_on"] = (dollar_down & (df["vix"] < df["vix_sma"])).astype(float)
    df.loc[df[["eur", "eur_20", "vix", "vix_sma"]].isna().any(axis=1), "risk_on"] = np.nan
    return df


def _asof(s: pd.Series, when) -> np.ndarray:
    s = s.dropna().sort_index()
    pos = s.index.searchsorted(when, side="right") - 1
    v = s.to_numpy(float)
    return np.where(pos >= 0, v[np.clip(pos, 0, None)], np.nan)


def conditional_forward(h: int = 30) -> pd.DataFrame:
    """Mean forward h-day BTC return (next open -> close h days later) by macro regime, block-bootstrap CIs."""
    btc = load("spot_BTCUSDT_1d")
    fwd = btc["close"].shift(-h) / btc["open"].shift(-1) - 1
    reg = macro_regime()["risk_on"]
    rows = []
    for name, mask in (("risk-on (dollar proxy down & VIX < 200d SMA)", reg == True),  # noqa: E712
                       ("rest", reg == False)):  # noqa: E712
        x = fwd[mask.fillna(False).astype(bool)].dropna().to_numpy()
        boot = block_bootstrap_mean(x, block=h)
        rows.append({"regime": name, "days": len(x), "mean_fwd": float(x.mean()),
                     "ci_lo": float(np.percentile(boot, 2.5)), "ci_hi": float(np.percentile(boot, 97.5))})
    on = fwd[(reg == True).fillna(False).astype(bool)].dropna()  # noqa: E712
    off = fwd[(reg == False).fillna(False).astype(bool)].dropna()  # noqa: E712
    # difference: bootstrap each side in blocks
    b_on, b_off = block_bootstrap_mean(on.to_numpy(), h, seed=5), block_bootstrap_mean(off.to_numpy(), h, seed=6)
    diff = b_on - b_off
    rows.append({"regime": "difference (risk-on − rest)", "days": len(on) + len(off),
                 "mean_fwd": float(on.mean() - off.mean()), "ci_lo": float(np.percentile(diff, 2.5)),
                 "ci_hi": float(np.percentile(diff, 97.5))})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------- D-5 overlay strategies
def macro_score() -> pd.Series:
    """VIX-only risk-on score (0-100): 100 - expanding percentile of VIX (>= 365 obs, history from 1990).
    Index = the time the value is known (00:00 UTC after the US session)."""
    vk = vix_known()
    return (100 - expanding_percentile(vk, 365)).rename("macro_score")


class S1Macro(RegimeFilter):
    """S1 (20-week SMA) with exposure = macro score / 100 while the filter is up; Monday rebalance,
    skipping drifts < 5% of equity."""
    key, name = "S1+macro", "S1 20w filter × macro score"
    GRID = {"sma": ["20w"]}

    def prepare(self):
        super().prepare()
        self.score = macro_score()

    def step(self, d, acct, prices):
        if d.dayofweek != 0:
            return
        up = self.sig(self.up, d) == True  # noqa: E712
        sc = self.sig(self.score, d)
        e = (sc / 100 if np.isfinite(sc) else 1.0) if up else 0.0
        px = prices.open.at[d, BTC]
        eq = acct.value({BTC: px})
        cur = acct.qty.get(BTC, 0.0) * px / eq if eq > 0 else 0.0
        if abs(cur - e) >= 0.05 or (e == 0 and cur > 0):
            acct.rebalance({BTC: e} if e > 0 else {}, {BTC: px}, min_frac=0.0)


class S2Macro(DCA200W):
    """S2 (aggressive table) with the weekly multiplier scaled by (0.5 + macro score / 100)."""
    key, name = "S2+macro", "S2 aggressive × macro score"
    GRID = {"table": ["aggressive"]}

    def prepare(self):
        super().prepare()
        self.score = macro_score()

    def multiplier(self, d):
        m = super().multiplier(d)
        sc = self.sig(self.score, d)
        return m * (0.5 + sc / 100) if np.isfinite(m) and np.isfinite(sc) else m
