#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


def read_env_symbols_from_file(env_path: Path) -> Optional[List[str]]:
    if not env_path.exists():
        return None
    syms = None
    for line in env_path.read_text().splitlines():
        if not line or line.strip().startswith("#"):
            continue
        if line.startswith("SYMBOLS="):
            val = line.split("=", 1)[1].strip()
            if val.startswith(("'", '"')) and val.endswith(("'", '"')):
                val = val[1:-1]
            syms = [s.strip() for s in val.split(",") if s.strip()]
            break
    return syms


def env_or_secrets_symbols(repo_root: Path) -> List[str]:
    v = os.getenv("SYMBOLS", "")
    if v.strip():
        return [s.strip() for s in v.split(",") if s.strip()]
    from_file = read_env_symbols_from_file(repo_root / "secrets.env")
    if from_file:
        return from_file
    raise SystemExit("SYMBOLS ei löydy ympäristöstä eikä secrets.env:stä")


def periods_per_year(tf: str) -> float:
    tf = tf.lower()
    if tf.endswith("m"):
        m = int(tf[:-1])
        return 525600.0 / m
    if tf.endswith("h"):
        h = int(tf[:-1])
        return 8760.0 / h
    if tf.endswith("d"):
        d = int(tf[:-1])
        return 252.0 / d
    return 8760.0


def load_ohlcv(symbol: str, tf: str) -> Optional[pd.DataFrame]:
    candidates = [
        Path("data/history") / f"{symbol}_{tf}.parquet",
        Path("data/history") / f"{symbol}_{tf}.csv",
        Path("data") / symbol / f"{tf}.parquet",
        Path("data") / symbol / f"{tf}.csv",
        Path("data") / f"{symbol}_{tf}.parquet",
        Path("data") / f"{symbol}_{tf}.csv",
    ]
    for fp in candidates:
        if fp.exists():
            try:
                if fp.suffix == ".parquet":
                    return pd.read_parquet(fp)
                return pd.read_csv(fp)
            except Exception:
                pass
    return None


def pct_returns(df: pd.DataFrame) -> np.ndarray:
    for col in ("close", "Close", "c", "CLOSE"):
        if col in df.columns:
            s = pd.Series(df[col]).astype(float)
            break
    else:
        s = pd.Series(df.iloc[:, -1]).astype(float)
    return s.pct_change().dropna().to_numpy()


def sharpe_ratio(returns: np.ndarray, tf: str, rf: float = 0.0) -> float:
    if returns.size == 0:
        return 0.0
    per = periods_per_year(tf)
    ex = returns - rf / per
    std = np.std(ex, ddof=1)
    if std == 0:
        return 0.0
    return float(np.mean(ex) / std * np.sqrt(per))


def sortino_ratio(returns: np.ndarray, tf: str, rf: float = 0.0) -> float:
    if returns.size == 0:
        return 0.0
    per = periods_per_year(tf)
    ex = returns - rf / per
    down = ex[ex < 0.0]
    dd = np.std(down, ddof=1) if down.size > 0 else 0.0
    if dd == 0:
        return 0.0
    return float(np.mean(ex) / dd * np.sqrt(per))


def max_drawdown(returns: np.ndarray) -> float:
    if returns.size == 0:
        return 0.0
    eq = np.cumprod(1.0 + returns)
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    return float(abs(np.min(dd)))  # positive


def profit_factor(returns: np.ndarray) -> float:
    if returns.size == 0:
        return 0.0
    gains = returns[returns > 0].sum()
    losses = -returns[returns < 0].sum()
    if losses == 0.0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / losses)


def robust_rank_scale(values: List[float], invert: bool = False) -> List[float]:
    if not values:
        return []
    arr = np.asarray(values, dtype=float)
    ranks = arr.argsort().argsort().astype(float)  # 0..n-1
    scaled = ranks / max(1, len(arr) - 1)
    return (1.0 - scaled).tolist() if invert else scaled.tolist()


def ensure_backfill(symbol: str, tf: str, days: int):
    # Try to backfill if no data file found
    if load_ohlcv(symbol, tf) is None:
        try:
            print(f"[backfill] {symbol} {tf} {days}")
            subprocess.run(
                ["python", "scripts/backfill.py", symbol, tf, str(days)],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser("Quick evaluate + select top-K from price returns")
    parser.add_argument("--timeframes", nargs="+", default=["15m", "1h", "4h"])
    parser.add_argument("--symbols", nargs="*", default=[])
    parser.add_argument("--lookback-days", type=int, default=int(os.getenv("EVAL_LOOKBACK_DAYS", "365")))
    parser.add_argument("--top-k", type=int, default=int(os.getenv("TOP_K", "5")))
    parser.add_argument("--min-trades", type=int, default=int(os.getenv("MIN_TRADES", "25")))
    parser.add_argument("--results-dir", default="results/metrics")
    parser.add_argument("--state-dir", default="state")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    symbols = args.symbols or env_or_secrets_symbols(repo_root)
    tfs = args.timeframes
    lookback_days = args.lookback_days

    print(f"[info] Evaluating {len(symbols)} symbols x {len(tfs)} TFs | lookback={lookback_days}d")
    Path(args.results_dir).mkdir(parents=True, exist_ok=True)
    Path(args.state_dir).mkdir(parents=True, exist_ok=True)

    all_items: List[Dict] = []
    for tf in tfs:
        items_tf: List[Dict] = []
        for sym in symbols:
            ensure_backfill(sym, tf, lookback_days)
            df = load_ohlcv(sym, tf)
            if df is None or df.empty:
                print(f"[warn] No data for {sym} {tf}")
                continue

            # Optional time filter by column name heuristics
            for tcol in ("time", "timestamp", "date", "Date"):
                if tcol in df.columns:
                    try:
                        df[tcol] = pd.to_datetime(df[tcol])
                        lb = pd.Timestamp.utcnow() - pd.Timedelta(days=lookback_days)
                        df = df[df[tcol] >= lb]
                    except Exception:
                        pass
                    break

            rets = pct_returns(df)
            if rets.size == 0:
                print(f"[warn] No returns for {sym} {tf}")
                continue

            wr = float((rets > 0).mean())
            pf = profit_factor(rets)
            sh = sharpe_ratio(rets, tf)
            so = sortino_ratio(rets, tf)
            mdd = max_drawdown(rets)
            avg = float(np.mean(rets))
            trades = int(rets.size)

            rec = dict(
                symbol=sym,
                tf=tf,
                trades=trades,
                winrate=wr,
                profit_factor=pf,
                sharpe=sh,
                sortino=so,
                max_drawdown=mdd,
                avg_trade_return=avg,
                exposure=1.0,
            )
            items_tf.append(rec)
            all_items.append(rec)

        (Path(args.results_dir) / f"metrics_{tf}.json").write_text(json.dumps(items_tf, indent=2))

    (Path(args.results_dir) / "metrics_all.json").write_text(json.dumps(all_items, indent=2))

    # Selection (aggregate by symbol: take best TF score)
    wr = [x["winrate"] for x in all_items]
    pf = [x["profit_factor"] for x in all_items]
    sh = [x["sharpe"] for x in all_items]
    dd = [x["max_drawdown"] for x in all_items]

    wr_s = robust_rank_scale(wr)
    pf_s = robust_rank_scale(pf)
    sh_s = robust_rank_scale(sh)
    dd_s = robust_rank_scale(dd, invert=True)  # lower dd better

    scored: List[Dict] = []
    for i, rec in enumerate(all_items):
        score = 0.5 * sh_s[i] + 0.3 * pf_s[i] + 0.2 * dd_s[i] + 0.0 * wr_s[i]
        scored.append({**rec, "score": float(score)})

    # group by symbol -> keep best score
    best_by_symbol: Dict[str, Dict] = {}
    for r in scored:
        sym = r["symbol"]
        if sym not in best_by_symbol or r["score"] > best_by_symbol[sym]["score"]:
            best_by_symbol[sym] = r

    eligible = [r for r in best_by_symbol.values() if r["trades"] >= args.min_trades]
    if not eligible:
        eligible = list(best_by_symbol.values())

    top = sorted(eligible, key=lambda r: r["score"], reverse=True)[: args.top_k]
    selection = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "timeframes": tfs,
        "top_k": args.top_k,
        "symbols": [r["symbol"] for r in top],
        "criteria": {
            "min_trades": args.min_trades,
            "weights": {"sharpe": 0.5, "profit_factor": 0.3, "max_drawdown": 0.2, "winrate": 0.0},
            "lookback_days": lookback_days,
        },
        "notes": "Quick selection from price returns (model-free).",
    }

    (Path(args.state_dir) / "active_symbols.json").write_text(json.dumps(selection, indent=2))
    print("[selection] -> state/active_symbols.json")
    print(json.dumps(selection, indent=2))


if __name__ == "__main__":
    main()
