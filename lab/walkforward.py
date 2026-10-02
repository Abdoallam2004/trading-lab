"""Walk-forward validation.

For every strategy family:
  * split history into rolling windows: optimise on TRAIN (e.g. 24 months),
    then trade the chosen config on the next, unseen TEST period (e.g. 12 months);
  * stitch all TEST periods together (capital carried over) = out-of-sample (OOS) record;
  * also run the exact specified rules ("spec", no optimisation) on the same OOS span,
    and every grid config on every TEST window to see whether the optimiser's pick
    beats a random/median pick (if not, the optimisation is just fitting noise).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import data as data_mod
from .config import DATA_DIR, CostModel, RiskModel
from .engine import BacktestResult, SymbolData, TradeCache, run_portfolio
from .indicators import add_indicators
from .metrics import group_stats, summarize, trade_stats
from .regime import BEAR, BULL, btc_regime, regime_at
from .strategies import SPEC_PARAMS, STRATEGIES, StrategyConfig, config_grid, make_setup
from .engine import ExitConfig


@dataclass(frozen=True)
class Criteria:
    """What an OOS record must show to PASS. Deliberately strict."""
    min_trades: int = 30
    min_profit_factor: float = 1.15
    min_expectancy_r: float = 0.05
    max_drawdown: float = 0.35
    min_positive_window_frac: float = 0.5
    min_train_trades: int = 20      # configs with fewer train trades cannot be selected
    degradation_flag: float = 0.5   # OOS expectancy < 50% of IS expectancy -> overfitting flag


@dataclass(frozen=True)
class Window:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp

    @property
    def label(self) -> str:
        return f"train {self.train_start:%Y-%m}..{self.train_end:%Y-%m} | test {self.test_start:%Y-%m}..{self.test_end:%Y-%m}"


def make_windows(data_start, data_end, train_months: int = 24, test_months: int = 12,
                 min_test_months: int = 3) -> list[Window]:
    data_start, data_end = pd.Timestamp(data_start), pd.Timestamp(data_end)
    out = []
    test_start = data_start + pd.DateOffset(months=train_months)
    while test_start + pd.DateOffset(months=min_test_months) <= data_end:
        test_end = min(test_start + pd.DateOffset(months=test_months), data_end)
        out.append(Window(test_start - pd.DateOffset(months=train_months), test_start, test_start, test_end))
        test_start = test_start + pd.DateOffset(months=test_months)
    return out


class Market:
    """Indicator frames + numpy views for every symbol/timeframe, with setup caching."""

    def __init__(self, frames: dict[str, dict[str, pd.DataFrame]], btc_daily: pd.DataFrame | None = None):
        self.ind = {tf: {s: add_indicators(df) for s, df in d.items() if len(df) > 0} for tf, d in frames.items()}
        self.sd = {tf: {s: SymbolData(s, df) for s, df in d.items()} for tf, d in self.ind.items()}
        if btc_daily is None:
            btc_daily = frames.get("1d", {}).get("BTCUSDT")
        self.regime = btc_regime(btc_daily) if btc_daily is not None else pd.Series(dtype=object)
        self._setups: dict = {}
        self.cache = TradeCache()

    @classmethod
    def from_cache(cls, symbols, timeframes=("1d", "4h"), data_dir=DATA_DIR) -> "Market":
        frames = {tf: {} for tf in timeframes}
        for tf in timeframes:
            for s in symbols:
                try:
                    frames[tf][s] = data_mod.load(s, tf, data_dir)
                except FileNotFoundError:
                    pass
        btc = None
        try:
            btc = data_mod.load("BTCUSDT", "1d", data_dir)
        except FileNotFoundError:
            pass
        return cls(frames, btc)

    @property
    def start(self) -> pd.Timestamp:
        return min(df.index[0] for d in self.ind.values() for df in d.values())

    @property
    def end(self) -> pd.Timestamp:
        return max(df.index[-1] for d in self.ind.values() for df in d.values())

    def setups(self, cfg: StrategyConfig):
        key = cfg.signal_key
        if key not in self._setups:
            self._setups[key] = {s: make_setup(d, cfg) for s, d in self.ind[cfg.timeframe].items()}
        return self._setups[key]

    def run(self, cfg: StrategyConfig, start=None, end=None, risk: RiskModel = RiskModel(),
            costs: CostModel = CostModel(), capital: float | None = None) -> BacktestResult:
        return run_portfolio(self.sd[cfg.timeframe], self.setups(cfg), cfg.exit, start, end, risk, costs,
                             initial_capital=capital, cache=self.cache)

    def annotate(self, trades: pd.DataFrame) -> pd.DataFrame:
        t = trades.copy()
        t["regime"] = regime_at(self.regime, t["entry_time"]) if len(t) else []
        t["year"] = t["entry_time"].dt.year if len(t) else []
        return t


def score(summary: dict, min_trades: int) -> float:
    """Selection objective on the TRAIN window: SQN-like expectancy_R * sqrt(n)."""
    n = summary["trades"]
    if n < min_trades or not np.isfinite(summary["expectancy_r"]):
        return -np.inf
    return summary["expectancy_r"] * np.sqrt(n)


@dataclass
class StrategyWF:
    strategy: str
    n_configs: int
    windows: list[dict]
    oos_trades: pd.DataFrame
    oos_equity: pd.Series
    oos: dict
    is_: dict
    spec_trades: pd.DataFrame
    spec_equity: pd.Series
    spec: dict
    spec_full_trades: pd.DataFrame
    spec_full: dict
    live_config: StrategyConfig | None
    verdict: str = "FAIL"
    flags: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def oos_score(self) -> float:
        n, e = self.oos["trades"], self.oos["expectancy_r"]
        return float(e * np.sqrt(n)) if n and np.isfinite(e) else -np.inf

    def by(self, col: str, which: str = "oos") -> pd.DataFrame:
        t = {"oos": self.oos_trades, "spec": self.spec_trades, "spec_full": self.spec_full_trades}[which]
        return group_stats(t, col)


def _stitch(market: Market, cfgs_by_window, windows, risk, costs):
    """Run each window's config on its TEST period, carrying capital forward."""
    capital = risk.initial_capital
    trades, curves = [], []
    for wi, (w, cfg) in enumerate(zip(windows, cfgs_by_window)):
        if cfg is None:
            continue
        res = market.run(cfg, w.test_start, w.test_end, risk, costs, capital)
        t = res.trades.assign(window=wi, config=cfg.label)
        trades.append(t)
        if len(res.equity):
            curves.append(res.equity)
            capital = float(res.equity.iloc[-1])
    tr = pd.concat(trades, ignore_index=True) if trades else pd.DataFrame(columns=["pnl", "r_multiple", "entry_time"])
    eq = pd.concat(curves) if curves else pd.Series(dtype=float)
    return market.annotate(tr) if len(tr) else tr, eq


def walk_forward(market: Market, strategies=STRATEGIES, timeframes=("1d", "4h"), windows=None,
                 risk: RiskModel = RiskModel(), costs: CostModel = CostModel(),
                 criteria: Criteria = Criteria(), train_months: int = 24, test_months: int = 12,
                 progress=print) -> list[StrategyWF]:
    windows = windows or make_windows(market.start, market.end, train_months, test_months)
    if not windows:
        raise ValueError("not enough history for a single walk-forward window")
    timeframes = [tf for tf in timeframes if tf in market.ind]
    results = []
    for strat in strategies:
        grid = config_grid(strat, timeframes)
        chosen, wrows = [], []
        is_trades = []
        for wi, w in enumerate(windows):
            best, best_score, best_res = None, -np.inf, None
            for cfg in grid:
                res = market.run(cfg, w.train_start, w.train_end, risk, costs)
                sc = score(summarize(res.trades, res.equity, res.initial_capital), criteria.min_train_trades)
                if sc > best_score:
                    best, best_score, best_res = cfg, sc, res
            # every config on TEST: does the optimiser's pick beat the median pick?
            test_exp = {}
            for cfg in grid:
                r = market.run(cfg, w.test_start, w.test_end, risk, costs)
                test_exp[cfg] = trade_stats(r.trades)["expectancy_r"]
            vals = np.array([v for v in test_exp.values() if np.isfinite(v)])
            row = {"window": w.label, "chosen": best.label if best else "none (no config met min trades)",
                   "train": summarize(best_res.trades, best_res.equity, best_res.initial_capital) if best else None,
                   "test_median_cfg_exp_r": float(np.median(vals)) if len(vals) else np.nan,
                   "test_frac_cfg_positive": float((vals > 0).mean()) if len(vals) else np.nan,
                   "chosen_test_exp_r": test_exp.get(best, np.nan) if best else np.nan,
                   "chosen_cfg": best}
            if best is not None:
                is_trades.append(best_res.trades)
            chosen.append(best)
            wrows.append(row)
            progress(f"  {strat:<9} {w.label}: {row['chosen']}")
        oos_trades, oos_eq = _stitch(market, chosen, windows, risk, costs)
        for wi, row in enumerate(wrows):
            wt = oos_trades[oos_trades["window"] == wi] if len(oos_trades) else oos_trades
            row["test"] = trade_stats(wt)
        is_all = pd.concat(is_trades, ignore_index=True) if is_trades else pd.DataFrame(columns=["pnl", "r_multiple"])

        spec_cfgs = {tf: StrategyConfig.make(strat, tf, SPEC_PARAMS[strat], ExitConfig("2R_3R")) for tf in timeframes}
        spec_cfg = spec_cfgs["1d"] if "1d" in spec_cfgs else next(iter(spec_cfgs.values()))
        spec_trades, spec_eq = _stitch(market, [spec_cfg] * len(windows), windows, risk, costs)
        full = market.run(spec_cfg, None, None, risk, costs)
        spec_full_trades = market.annotate(full.trades)

        # live config: optimise on the most recent TRAIN-length period ending at the last bar
        live_start = market.end - pd.DateOffset(months=train_months)
        live, live_score = None, -np.inf
        for cfg in grid:
            res = market.run(cfg, live_start, market.end + pd.Timedelta(seconds=1), risk, costs)
            sc = score(summarize(res.trades, res.equity, res.initial_capital), criteria.min_train_trades)
            if sc > live_score:
                live, live_score = cfg, sc

        wf = StrategyWF(
            strategy=strat, n_configs=len(grid), windows=wrows,
            oos_trades=oos_trades, oos_equity=oos_eq,
            oos=summarize(oos_trades, oos_eq, risk.initial_capital) if len(oos_eq) else trade_stats(oos_trades),
            is_=trade_stats(is_all),
            spec_trades=spec_trades, spec_equity=spec_eq,
            spec=summarize(spec_trades, spec_eq, risk.initial_capital) if len(spec_eq) else trade_stats(spec_trades),
            spec_full_trades=spec_full_trades,
            spec_full=summarize(full.trades, full.equity, full.initial_capital),
            live_config=live,
        )
        judge(wf, criteria)
        results.append(wf)
    return sorted(results, key=lambda r: (r.verdict != "PASS", -r.oos_score))


def judge(wf: StrategyWF, c: Criteria) -> None:
    """Fill verdict, failure reasons and overfitting flags."""
    o, reasons, flags = wf.oos, [], []
    n = o.get("trades", 0)
    pf, exp = o.get("profit_factor", np.nan), o.get("expectancy_r", np.nan)
    dd = o.get("max_drawdown", np.nan)
    if n < c.min_trades:
        reasons.append(f"only {n} OOS trades (< {c.min_trades})")
    if not (np.isfinite(pf) and pf >= c.min_profit_factor) and not (pf == np.inf and n > 0):
        reasons.append(f"OOS profit factor {pf:.2f} < {c.min_profit_factor}")
    if not (np.isfinite(exp) and exp >= c.min_expectancy_r):
        reasons.append(f"OOS expectancy {exp:+.3f}R < {c.min_expectancy_r}R")
    if np.isfinite(dd) and dd > c.max_drawdown:
        reasons.append(f"OOS max drawdown {dd:.1%} > {c.max_drawdown:.0%}")
    tested = [r for r in wf.windows if r["test"]["trades"] > 0]
    pos = [r for r in tested if r["test"]["expectancy_r"] > 0]
    if tested and len(pos) / len(wf.windows) < c.min_positive_window_frac:
        reasons.append(f"positive in only {len(pos)}/{len(wf.windows)} OOS windows")

    is_exp = wf.is_.get("expectancy_r", np.nan)
    if np.isfinite(is_exp) and is_exp > 0 and np.isfinite(exp) and exp < c.degradation_flag * is_exp:
        drop = 1 - exp / is_exp
        flags.append(f"OVERFIT: OOS expectancy {exp:+.3f}R vs in-sample {is_exp:+.3f}R ({drop:.0%} worse)")
    picks = [r["chosen_cfg"] for r in wf.windows if r["chosen_cfg"] is not None]
    if len(picks) >= 3 and len(set(picks)) == len(picks):
        flags.append("UNSTABLE: optimiser picked a different config in every window")
    diffs = [r["chosen_test_exp_r"] - r["test_median_cfg_exp_r"] for r in wf.windows
             if np.isfinite(r["chosen_test_exp_r"]) and np.isfinite(r["test_median_cfg_exp_r"])]
    if diffs and np.mean(diffs) <= 0:
        flags.append("NO EDGE FROM OPTIMISING: the chosen config did no better OOS than the median config")
    se = wf.spec.get("expectancy_r", np.nan)
    if np.isfinite(se) and np.isfinite(exp) and se > exp:
        flags.append(f"Spec rules (no optimisation) beat the optimised version OOS ({se:+.3f}R vs {exp:+.3f}R)")
    if len(wf.oos_trades):
        reg = group_stats(wf.oos_trades, "regime")
        good = [k for k in (BULL, BEAR) if k in reg.index and reg.loc[k, "trades"] >= 10 and reg.loc[k, "expectancy_r"] > 0]
        bad = [k for k in (BULL, BEAR) if k in reg.index and reg.loc[k, "trades"] >= 10 and reg.loc[k, "expectancy_r"] <= 0]
        if good and bad:
            flags.append(f"REGIME-DEPENDENT: works only when {good[0]} (loses when {bad[0]})")
        coin = wf.oos_trades.groupby("symbol")["pnl"].sum()
        total = coin.sum()
        if total > 0 and coin.max() > 0.5 * total:
            flags.append(f"CONCENTRATED: {coin.idxmax()} made {coin.max() / total:.0%} of OOS profit")
    wf.reasons, wf.flags = reasons, flags
    wf.verdict = "PASS" if not reasons else "FAIL"
