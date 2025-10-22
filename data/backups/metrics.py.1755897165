from __future__ import annotations
import numpy as np

def equity_curve(ret_series: np.ndarray, start_equity: float = 1.0) -> np.ndarray:
    r = np.asarray(ret_series, dtype=float)
    eq = [start_equity]
    for x in r:
        eq.append(eq[-1] * (1.0 + x))
    return np.asarray(eq[1:], float)

def max_drawdown(equity: np.ndarray) -> float:
    eq = np.asarray(equity, float)
    if eq.size == 0:
        return 0.0
    peaks = np.maximum.accumulate(eq)
    dd = (eq - peaks) / peaks
    return float(-dd.min() * 100.0)

def hitrate(pnl: np.ndarray) -> float:
    p = np.asarray(pnl, float)
    return float((p > 0).mean() * 100.0) if p.size else 0.0

def profit_factor(pnl: np.ndarray) -> float:
    p = np.asarray(pnl, float)
    gains = p[p > 0].sum()
    losses = -p[p < 0].sum()
    return float(gains / (losses if losses > 0 else 1e-12))

def sharpe_ratio(pnl: np.ndarray, periods_per_year: int = 252) -> float:
    p = np.asarray(pnl, float)
    if p.size == 0:
        return 0.0
    mu = p.mean()
    sd = p.std(ddof=1)
    return float((mu / sd) * (periods_per_year ** 0.5)) if sd > 0 else 0.0
