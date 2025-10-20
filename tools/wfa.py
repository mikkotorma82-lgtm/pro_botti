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
