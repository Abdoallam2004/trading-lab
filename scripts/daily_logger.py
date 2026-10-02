"""Lab 4 phase F-1: forward data logger (the new holdout).

Run once a day at 00:10 UTC. Appends one row per asset to data/forward/market.csv and one row per
alive rule to data/forward/rules.csv (idempotent per UTC date). Only public endpoints, no API key.

    python scripts/daily_logger.py            # log today
    python scripts/daily_logger.py --dry-run  # print, do not write

Scheduling
  cron (Linux/macOS):   10 0 * * *  cd /path/to/trading-lab && .venv/bin/python scripts/daily_logger.py >> data/forward/logger.log 2>&1
  GitHub Actions:       copy ops/github-actions-daily-logger.yml to .github/workflows/ (it commits data/forward/)
Liquidations: Binance's force-order endpoint needs an API key, so they are not logged (a column records why).
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "forward"
FAPI = "https://fapi.binance.com"
SPOT = "https://api.binance.com"
FNG = "https://api.alternative.me/fng/?limit=1"
ASSETS = ("BTCUSDT", "ETHUSDT")
FROZEN = ROOT / "reports" / "lab4_frozen.json"


def get(url, params=None, session=None):
    s = session or requests
    r = s.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()


# ----------------------------------------------------------------------------- parsers (unit-tested)
def parse_premium(j: dict) -> dict:
    return {"mark_price": float(j["markPrice"]), "index_price": float(j["indexPrice"]),
            "last_funding_rate": float(j["lastFundingRate"]),
            "premium": float(j["markPrice"]) / float(j["indexPrice"]) - 1}


def parse_last(rows: list, field: str) -> float:
    return float(rows[-1][field]) if rows else float("nan")


def parse_spot_kline(rows: list) -> dict:
    """Last CLOSED daily kline (the API's last row is the running day)."""
    k = rows[-2]
    qv, tbq = float(k[7]), float(k[10])
    return {"spot_open_time": int(k[0]), "spot_close": float(k[4]), "spot_quote_volume": qv,
            "taker_buy_quote": tbq, "taker_delta": 2 * tbq - qv}


def parse_fng(j: dict) -> dict:
    d = j["data"][0]
    return {"fear_greed": int(d["value"]), "fear_greed_label": d["value_classification"],
            "fear_greed_time": int(d["timestamp"])}


# ----------------------------------------------------------------------------- rule states
def weekly_closes(session=None) -> list[float]:
    rows = get(f"{SPOT}/api/v3/klines", {"symbol": "BTCUSDT", "interval": "1w", "limit": 210}, session)
    return [float(r[4]) for r in rows[:-1]]   # completed weeks only


def rule_states(weekly: list[float], frozen: dict) -> list[dict]:
    out = []
    for rule in frozen.get("accumulation", []):
        if rule["id"] == "S2-aggressive" and len(weekly) >= 200:
            sma = sum(weekly[-200:]) / 200
            ratio = weekly[-1] / sma
            mult = next(m for ub, m in rule["table"] if ratio < ub)
            out.append({"rule": rule["id"], "signal": f"ratio={ratio:.3f}", "action": f"weekly buy x{mult}",
                        "level": f"200w SMA={sma:.0f}", "trim": ratio > rule["trim_at"]})
        if rule["id"] == "S1-20w" and len(weekly) >= 20:
            sma = sum(weekly[-20:]) / 20
            up = weekly[-1] > sma
            out.append({"rule": rule["id"], "signal": "up" if up else "down",
                        "action": "hold BTC" if up else "hold cash", "level": f"20w SMA={sma:.0f}", "trim": False})
    for rule in frozen.get("paper_trading", []):
        out.append({"rule": rule["id"], "signal": "see rule", "action": "evaluate manually", "level": "", "trim": False})
    return out


def append(path: Path, row: dict, key=("date", "asset")):
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    if path.exists():
        with path.open() as fh:
            rows = list(csv.DictReader(fh))
    k = tuple(str(row.get(x, "")) for x in key)
    rows = [r for r in rows if tuple(r.get(x, "") for x in key) != k] + [{c: row.get(c, "") for c in row}]
    cols = list(dict.fromkeys(c for r in rows for c in r))
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def collect(session=None) -> tuple[list[dict], list[dict]]:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    market = []
    try:
        fng = parse_fng(get(FNG, session=session))
    except Exception as e:  # noqa: BLE001
        fng = {"fear_greed_error": str(e)[:120]}
    for a in ASSETS:
        row = {"date": today, "asset": a, "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "liquidations": "not logged: Binance force orders need an API key"}
        calls = {
            "premium": lambda: parse_premium(get(f"{FAPI}/fapi/v1/premiumIndex", {"symbol": a}, session)),
            "oi": lambda: {"open_interest": float(get(f"{FAPI}/fapi/v1/openInterest", {"symbol": a}, session)
                                                  ["openInterest"])},
            "global_ls": lambda: {"global_long_short": parse_last(get(
                f"{FAPI}/futures/data/globalLongShortAccountRatio", {"symbol": a, "period": "1d", "limit": 1},
                session), "longShortRatio")},
            "top_ls": lambda: {"top_long_short_positions": parse_last(get(
                f"{FAPI}/futures/data/topLongShortPositionRatio", {"symbol": a, "period": "1d", "limit": 1},
                session), "longShortRatio")},
            "taker": lambda: {"taker_buy_sell_ratio": parse_last(get(
                f"{FAPI}/futures/data/takerlongshortRatio", {"symbol": a, "period": "1d", "limit": 1},
                session), "buySellRatio")},
            "spot": lambda: parse_spot_kline(get(f"{SPOT}/api/v3/klines",
                                                 {"symbol": a, "interval": "1d", "limit": 2}, session)),
        }
        for name, fn in calls.items():
            try:
                row.update(fn())
            except Exception as e:  # noqa: BLE001  (keep logging the rest)
                row[f"{name}_error"] = str(e)[:120]
        row.update(fng)
        market.append(row)
    rules = []
    try:
        frozen = json.loads(FROZEN.read_text()) if FROZEN.exists() else {}
        for r in rule_states(weekly_closes(session), frozen):
            rules.append({"date": today, **r})
    except Exception as e:  # noqa: BLE001
        rules.append({"date": today, "rule": "ALL", "signal": "error", "action": str(e)[:120]})
    return market, rules


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    market, rules = collect()
    if args.dry_run:
        print(json.dumps({"market": market, "rules": rules}, indent=1))
        return
    for r in market:
        append(OUT / "market.csv", r)
    for r in rules:
        append(OUT / "rules.csv", r, key=("date", "rule"))
    print(f"logged {len(market)} market rows and {len(rules)} rule rows to {OUT}")


if __name__ == "__main__":
    main()
