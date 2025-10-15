#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from dataclasses import dataclass
from typing import Dict, Any, List, Tuple

import numpy as np
import pandas as pd

@dataclass
class FoldResult:
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    n: int
    sharpe_oos: float
    pf_oos: float
    wr_oos: float
    cagr_oos: float
    maxdd_oos: float

def _metrics(returns: np.ndarray) -> Tuple[float,float,float,float]:
    if returns.size == 0:
        return 0.0, 1.0, 0.0, 0.0
    mu = returns.mean()
    sd = returns.std(ddof=1) or 1e-12
    sharpe = mu / sd
    gains = returns[returns > 0].sum()
    losses = -returns[returns < 0].sum()
    pf = (gains / losses) if losses > 0 else float("inf")
    wr = (returns > 0).mean() if returns.size else 0.0
    cagr = float(np.exp(np.log1p(returns).sum()) - 1.0)
    return float(sharpe), float(pf), float(wr), float(cagr)

def _max_drawdown(equity: np.ndarray) -> float:
    if equity.size == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak
    return float(dd.min())

def _sma_strategy(df: pd.DataFrame, n: int) -> np.ndarray:
    px = df["close"].astype(float).values
    sma = pd.Series(px).rolling(n, min_periods=n).mean().values
    pos = (px > sma).astype(float)
    ret = np.zeros_like(px, dtype=float)
    ret[1:] = (px[1:] - px[:-1]) / (px[:-1] + 1e-12) * pos[:-1]
    return ret

def wfa_one(csv_path: str, folds: int = 6) -> Dict[str, Any]:
    df = pd.read_csv(csv_path)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
        df = df.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)
    need = {"time","close"}
    if not need.issubset(set(df.columns)):
        raise ValueError(f"{csv_path} must contain columns: {sorted(list(need))}")
    n_candidates = [10, 20, 50]
    T = len(df)
    if T < 400:
        raise ValueError(f"Not enough rows ({T}) for WFA")
    fold_len = T // (folds + 1)
    results: List[FoldResult] = []

    for i in range(folds):
        train_lo = 0
        train_hi = (i+1)*fold_len
        test_lo = train_hi
        test_hi = min((i+2)*fold_len, T)
        dtrain = df.iloc[train_lo:train_hi]
        dtest = df.iloc[test_lo:test_hi]
        if len(dtest) < 100:
            break
        # select best n on train
        best_n = None
        best_sh = -1e9
        for n in n_candidates:
            r = _sma_strategy(dtrain, n)
            sh, *_ = _metrics(r)
            if sh > best_sh:
                best_sh = sh
                best_n = n
        # apply on test
        rtest = _sma_strategy(dtest, int(best_n))
        sh, pf, wr, cagr = _metrics(rtest)
        eq = np.cumprod(1.0 + rtest)
        maxdd = _max_drawdown(eq)
        results.append(FoldResult(
            train_start=str(dtrain["time"].iloc[0]),
            train_end=str(dtrain["time"].iloc[-1]),
            test_start=str(dtest["time"].iloc[0]),
            test_end=str(dtest["time"].iloc[-1]),
            n=int(best_n),
            sharpe_oos=sh, pf_oos=pf, wr_oos=wr, cagr_oos=cagr, maxdd_oos=maxdd
        ))

    agg = {
        "file": csv_path,
        "folds": len(results),
        "sharpe_oos_mean": float(np.mean([r.sharpe_oos for r in results])) if results else 0.0,
        "pf_oos_mean": float(np.mean([r.pf_oos for r in results])) if results else 1.0,
        "wr_oos_mean": float(np.mean([r.wr_oos for r in results])) if results else 0.0,
        "cagr_oos_prod": float(np.prod([1+r.cagr_oos for r in results]) - 1.0) if results else 0.0,
        "maxdd_oos_min": float(np.min([r.maxdd_oos for r in results])) if results else 0.0,
        "detail": [r.__dict__ for r in results],
    }
    return agg

def _cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="Input CSV with columns [time, open, high, low, close, volume]")
    ap.add_argument("--folds", type=int, default=6)
    ap.add_argument("--out", required=True, help="Output JSON path")
    args = ap.parse_args()

    res = wfa_one(args.csv, folds=args.folds)
    with open(args.out, "w") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(f"[OK] WFA -> {args.out}")

if __name__ == "__main__":
    _cli()
