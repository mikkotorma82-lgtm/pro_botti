"""
Enhanced trading metrics calculation.
Provides comprehensive performance metrics for post-train evaluation.
"""
from __future__ import annotations
import numpy as np
from typing import Dict, Any


def calculate_metrics(
    returns: np.ndarray,
    signals: np.ndarray | None = None,
    periods_per_year: int = 252
) -> Dict[str, Any]:
    """
    Calculate comprehensive trading metrics from return series.
    
    Args:
        returns: Array of trade returns (e.g., pnl per trade or per bar)
        signals: Optional array of signals (1=long, -1=short, 0=flat)
        periods_per_year: Number of periods in a year (252 for daily, etc.)
    
    Returns:
        Dictionary containing all calculated metrics
    """
    ret = np.asarray(returns, dtype=float)
    
    if ret.size == 0:
        return _empty_metrics()
    
    # Filter out zero/NaN returns for trade-based metrics
    trades = ret[~np.isnan(ret) & (ret != 0)]
    n_trades = len(trades)
    
    metrics = {
        "trades": n_trades,
        "winrate": winrate(trades),
        "profit_factor": profit_factor(trades),
        "sharpe": sharpe_ratio(ret, periods_per_year),
        "sortino": sortino_ratio(ret, periods_per_year),
        "max_drawdown": max_drawdown_from_returns(ret),
        "avg_trade_return": avg_trade_return(trades),
        "exposure": exposure(signals) if signals is not None else 0.0,
        "total_return": float(np.sum(ret)) if ret.size > 0 else 0.0,
        "avg_return": float(np.mean(ret)) if ret.size > 0 else 0.0,
    }
    
    return metrics


def _empty_metrics() -> Dict[str, Any]:
    """Return empty/zero metrics when no data available."""
    return {
        "trades": 0,
        "winrate": 0.0,
        "profit_factor": 0.0,
        "sharpe": 0.0,
        "sortino": 0.0,
        "max_drawdown": 0.0,
        "avg_trade_return": 0.0,
        "exposure": 0.0,
        "total_return": 0.0,
        "avg_return": 0.0,
    }


def winrate(returns: np.ndarray) -> float:
    """Calculate win rate as percentage."""
    ret = np.asarray(returns, dtype=float)
    if ret.size == 0:
        return 0.0
    return float((ret > 0).sum() / ret.size * 100.0)


def profit_factor(returns: np.ndarray) -> float:
    """Calculate profit factor (total wins / total losses)."""
    ret = np.asarray(returns, dtype=float)
    if ret.size == 0:
        return 0.0
    gains = ret[ret > 0].sum()
    losses = -ret[ret < 0].sum()
    return float(gains / max(losses, 1e-12))


def sharpe_ratio(returns: np.ndarray, periods_per_year: int = 252) -> float:
    """Calculate annualized Sharpe ratio."""
    ret = np.asarray(returns, dtype=float)
    if ret.size == 0:
        return 0.0
    mu = ret.mean()
    sd = ret.std(ddof=1)
    if sd == 0:
        return 0.0
    return float((mu / sd) * np.sqrt(periods_per_year))


def sortino_ratio(returns: np.ndarray, periods_per_year: int = 252, target: float = 0.0) -> float:
    """Calculate annualized Sortino ratio (downside deviation)."""
    ret = np.asarray(returns, dtype=float)
    if ret.size == 0:
        return 0.0
    mu = ret.mean()
    downside = ret[ret < target]
    if downside.size == 0:
        return 0.0
    downside_std = downside.std(ddof=1)
    if downside_std == 0:
        return 0.0
    return float((mu - target) / downside_std * np.sqrt(periods_per_year))


def max_drawdown_from_returns(returns: np.ndarray) -> float:
    """Calculate maximum drawdown percentage from return series."""
    ret = np.asarray(returns, dtype=float)
    if ret.size == 0:
        return 0.0
    
    # Build equity curve
    equity = np.cumprod(1.0 + ret)
    if equity.size == 0:
        return 0.0
    
    # Calculate drawdown
    peaks = np.maximum.accumulate(equity)
    dd = (equity - peaks) / peaks
    max_dd = float(-dd.min() * 100.0)
    return max_dd


def avg_trade_return(returns: np.ndarray) -> float:
    """Calculate average return per trade."""
    ret = np.asarray(returns, dtype=float)
    if ret.size == 0:
        return 0.0
    return float(ret.mean())


def exposure(signals: np.ndarray) -> float:
    """Calculate market exposure as percentage of time in position."""
    sig = np.asarray(signals, dtype=float)
    if sig.size == 0:
        return 0.0
    in_position = np.abs(sig) > 0
    return float(in_position.sum() / sig.size * 100.0)
