"""Lab 2 report: markdown, equity CSV, PNG charts."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .evaluate import BENCH, FULL, IS, OOS, SEGMENTS  # noqa: E402
from .sim import twr_returns  # noqa: E402

# validated categorical slots 1-4 (dataviz reference palette, light surface)
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
INK, INK2, MUTED, GRID, AXIS, SURFACE, OTHER = ("#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7",
                                                "#fcfcfb", "#c9c8c1")


def f(x, kind="num"):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "–"
    return {"pct": f"{x:.1%}", "x": f"{x:.2f}×", "usd": f"${x:,.0f}", "int": f"{int(x)}", "btc": f"{x:.4f}",
            "num": f"{x:.2f}"}[kind]


def table(headers, rows) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    return "\n".join(out + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


A_COLS = [("Final", "final", "usd"), ("CAGR", "cagr", "pct"), ("Max DD", "max_dd", "pct"), ("Calmar", "calmar", "num"),
          ("Sharpe", "sharpe", "num"), ("In market", "time_in_market", "pct"), ("Fills", "trades", "int"),
          ("Turnover/yr", "turnover", "x")]
B_COLS = [("Value÷contrib.", "multiple", "x"), ("IRR", "irr", "pct"), ("Max DD", "max_dd", "pct"),
          ("Calmar", "calmar", "num"), ("Sharpe", "sharpe", "num"), ("BTC per $1k", "btc_per_1k", "btc"),
          ("In market", "time_in_market", "pct"), ("Fills", "trades", "int"), ("Turnover/yr", "turnover", "x")]


def cols(frame):
    return A_COLS if frame == "A" else B_COLS


def metric_row(m, frame):
    return [f(m[k], kind) for _, k, kind in cols(frame)]


def sort_key(fr):
    m = fr.oos
    return -(m["calmar"] if fr.frame == "A" else m["multiple"])


def build_markdown(results: dict, ev, look: list[dict], notes: dict) -> str:
    """results[strategy_cls] = {"A": FrameResult, "B": FrameResult}."""
    L = []
    L.append("# Lab 2 — BTC-centric halal strategies (spot, long-only)\n")
    L.append("## Verdict\n")
    L.append(notes["verdict"] + "\n")

    for frame, title, bname in (("A", "Frame A — lump sum $10,000", "B1 buy & hold"),
                                ("B", "Frame B — $100 every Monday", "B2 weekly DCA")):
        b = ev.bench(frame, OOS)
        L.append(f"## Ranking by out-of-sample result — {title}\n")
        L.append(f"Out-of-sample = {OOS[0]} → {OOS[1]}, run once with parameters chosen on {IS[0]} → {IS[1]}. "
                 f"Sorted by {'Calmar' if frame == 'A' else 'final value ÷ contributed'}.\n")
        rows = [["", f"**{bname}** (benchmark)", "–", "–"] + metric_row(b, frame)]
        ranked = sorted(results.items(), key=lambda kv: sort_key(kv[1][frame]))
        for i, (cls, frs) in enumerate(ranked, 1):
            fr = frs[frame]
            rows.append([i, f"**{cls.key}** {cls.name}", label_md(fr.label), f"`{param_str(fr.chosen)}`"]
                        + metric_row(fr.oos, frame))
        L.append(table(["#", "Strategy", "Label", "Params"] + [c[0] for c in cols(frame)], rows))
        L.append("")
        L.append(f"![{title}: out-of-sample equity and drawdown](lab2_oos_frame{frame}.png)\n")

    L.append("## Per-strategy results\n")
    L.append("Each row is a separate run starting fresh at the period start (frame A: $10,000; frame B: $0 plus "
             "$100 each Monday). IS and OOS are what the verdict uses; full period and cycles are context.\n")
    for cls, frs in results.items():
        L.append(f"### {cls.key} — {cls.name}\n")
        L.append(f"{(cls.__doc__ or '').strip()}\n")
        L.append(f"Parameter grid (fixed before testing): `{cls.GRID}`\n")
        for frame in ("A", "B"):
            fr = frs[frame]
            L.append(f"**Frame {frame}: {label_md(fr.label)}** — chosen `{param_str(fr.chosen)}` ({fr.why}).  ")
            for r in fr.reasons:
                L.append(f"- {r}")
            nb = ", ".join(f"`{param_str(q)}` {'✅' if ok else '❌'}" for q, ok in fr.neighbour_pass)
            L.append(f"- neighbours (OOS vs benchmark): {nb or '–'}")
            sh = ", ".join(f"{k} {f(v, 'pct')}" for k, v in fr.shares.items())
            L.append(f"- share of full-period profit by cycle: {sh}")
            if fr.oos_trades is not None:
                L.append(f"- OOS round-trip trades: {fr.oos_trades}")
            L.append("")
            bench = BENCH[frame]
            rows = []
            for name, period in (("In-sample", IS), ("Out-of-sample", OOS), ("Full period", FULL), *SEGMENTS.items()):
                rows.append([name, f"{period[0][:7]}→{period[1][:7]}"] + metric_row(ev.run(cls, fr.chosen, period, frame)[0], frame))
                rows.append([f"↳ {bench.key}", ""] + metric_row(ev.run(bench, {}, period, frame)[0], frame))
            L.append(table(["Period", "Dates"] + [c[0] for c in cols(frame)], rows))
            L.append("")

    L.append("### S7b — Brad Goh setups\n")
    L.append("**Not tested — no spec.** The repository contains no written specification of \"Brad Goh setups\"; "
             "inventing one would be untestable folklore, so S7b was skipped as instructed.\n")

    L.append("## Look-ahead tests\n")
    L.append("Unit tests (`tests/test_lab2.py`, synthetic data, run on every commit):\n")
    L.append("- every signal (SMA regimes, 200w ratio, ATH drawdown, log-regression z, MVRV-Z, momentum, ZigZag pivots) "
             "is unchanged up to t when one more bar is appended;")
    L.append("- every strategy × frame produces an identical equity curve up to t when run on data ending at t vs t+1;")
    L.append("- every strategy × frame makes identical trades at day t's open when day t's close is shocked ×0.5 / ×1.5 "
             "(verified to catch an injected same-day look-ahead bug in 11 of 14 signal-driven cases; the remaining "
             "cases cannot be affected by that bug on the tested dates).\n")
    ok = sum(r["ok"] for r in look)
    L.append(f"Real-data check (all inputs rebuilt from data ending at t and at t+1, chosen parameters, both frames): "
             f"**{ok}/{len(look)} identical**.\n")
    L.append(table(["Strategy", "Params", "Frame", "Cutoff t", "Max |diff| up to t", "OK"],
                   [[r["strategy"], f"`{param_str(r['params'])}`", r["frame"], r["cutoff"], f"{r['max_abs_diff']:.2e}",
                     "✅" if r["ok"] else "❌"] for r in look]))
    L.append("")
    L.append("## Data, gaps and assumptions\n")
    L += [f"- {x}" for x in notes["assumptions"]]
    L.append("")
    return "\n".join(L) + "\n"


def label_md(label):
    return {"PASS": "✅ PASS", "FAIL": "❌ FAIL", "INCONCLUSIVE": "⚠️ INCONCLUSIVE"}[label]


def param_str(p):
    return ", ".join(f"{k}={v}" for k, v in p.items()) or "–"


def equity_frame(results: dict, ev) -> pd.DataFrame:
    rows = []
    for frame in ("A", "B"):
        for period_name, period in (("OOS", OOS), ("FULL", FULL)):
            series = [(BENCH[frame].key, BENCH[frame], {})] + [(c.key, c, frs[frame].chosen) for c, frs in results.items()]
            for key, cls, params in series:
                res = ev.run(cls, params, period, frame)[1]
                nav = (1 + twr_returns(res)).cumprod()
                rows.append(pd.DataFrame({"date": res.equity.index.strftime("%Y-%m-%d"), "frame": frame,
                                          "period": period_name, "series": key, "params": param_str(params),
                                          "equity": res.equity.round(2).values,
                                          "contributed": res.flows.cumsum().round(2).values,
                                          "growth_of_1": nav.round(6).values,
                                          "drawdown": (nav / nav.cummax() - 1).round(6).values}))
    return pd.concat(rows, ignore_index=True)


def charts(eq: pd.DataFrame, results: dict, out: Path) -> list[Path]:
    paths = []
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": AXIS,
                         "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED})
    for frame in ("A", "B"):
        for period in ("OOS", "FULL"):
            d = eq[(eq.frame == frame) & (eq.period == period)]
            bench = "B1" if frame == "A" else "B2"
            ranked = [c.key for c, _ in sorted(results.items(), key=lambda kv: sort_key(kv[1][frame]))]
            b_curve = d[d.series == bench].growth_of_1.to_numpy()
            ties = [k for k in ranked if np.allclose(d[d.series == k].growth_of_1.to_numpy(), b_curve, rtol=0, atol=1e-9)]
            ranked = [k for k in ranked if k not in ties]  # identical to the benchmark: drawn as one line
            top, rest = ranked[:4], ranked[4:]
            bench_label = f"{bench} benchmark" + (f" = {', '.join(ties)} (identical)" if ties else "")
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]},
                                           facecolor=SURFACE)
            for ax in (ax1, ax2):
                ax.set_facecolor(SURFACE)
                ax.grid(True, color=GRID, linewidth=0.6)
                ax.spines[["top", "right"]].set_visible(False)
            order = [(k, OTHER, 1.0, "other strategies" if i == 0 else None) for i, k in enumerate(rest)]
            order += [(k, SERIES[i], 2.0, k) for i, k in enumerate(top)]
            order += [(bench, INK, 2.0, bench_label)]
            for key, color, lw, lab in order:
                s = d[d.series == key]
                x = pd.to_datetime(s.date)
                ax1.plot(x, s.growth_of_1, color=color, linewidth=lw, label=lab, solid_capstyle="round")
                ax2.plot(x, s.drawdown * 100, color=color, linewidth=lw * 0.75)
            ax1.set_yscale("log")
            # direct labels at the line ends, nudged apart (log space) so they never overlap
            ends = sorted(((np.log10(d[d.series == k].growth_of_1.iloc[-1]), k) for k in top + [bench]))
            lo, hi = np.log10(ax1.get_ylim())
            gap, placed = (hi - lo) * 0.035, []
            for y, k in ends:
                y = max(y, placed[-1] + gap) if placed else y
                placed.append(y)
                text = f"{k} = {', '.join(ties)}" if k == bench and ties else k
                ax1.annotate(text, (pd.to_datetime(d.date.iloc[-1]), 10 ** y), xytext=(4, 0),
                             textcoords="offset points", va="center", fontsize=8, color=INK2, annotation_clip=False)
            fmt = matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}")
            ax1.yaxis.set_major_formatter(fmt)
            ax1.yaxis.set_minor_formatter(fmt)
            ax1.tick_params(axis="y", which="minor", labelsize=7)
            ax1.set_ylabel("Growth of $1 (time-weighted, log)")
            ax2.set_ylabel("Drawdown (%)")
            span = OOS if period == "OOS" else FULL
            what = "lump sum $10,000" if frame == "A" else "$100 every Monday"
            ax1.set_title(f"Frame {frame} ({what}) — {'out-of-sample' if period == 'OOS' else 'full period'} "
                          f"{span[0]} → {span[1]}", loc="left", color=INK, fontsize=11)
            ax1.legend(loc="upper left", frameon=False, fontsize=8, ncol=3, labelcolor=INK2)
            fig.tight_layout()
            p = out / f"lab2_{period.lower()}_frame{frame}.png"
            fig.savefig(p, dpi=130, facecolor=SURFACE)
            plt.close(fig)
            paths.append(p)
    return paths
