"""
Top-K symbol selector with composite scoring.
Selects best trading symbols based on multi-criteria evaluation.
"""
from __future__ import annotations
import numpy as np
from typing import List, Dict, Any
from loguru import logger


def select_top_symbols(
    metrics_list: List[Dict[str, Any]],
    top_k: int = 5,
    min_trades: int = 25,
    weights: Dict[str, float] | None = None,
) -> List[Dict[str, Any]]:
    """
    Select top-K symbols based on composite scoring.
    
    Args:
        metrics_list: List of dicts with keys: symbol, tf, sharpe, profit_factor, max_drawdown, winrate, trades
        top_k: Number of top symbols to select
        min_trades: Minimum trades threshold to be eligible
        weights: Scoring weights dict with keys: sharpe, profit_factor, max_drawdown, winrate
    
    Returns:
        List of top-K symbols sorted by composite score (descending)
    """
    if weights is None:
        weights = {
            "sharpe": 0.5,
            "profit_factor": 0.3,
            "max_drawdown": 0.2,
            "winrate": 0.0,
        }
    
    # Filter by min_trades
    eligible = [m for m in metrics_list if m.get("trades", 0) >= min_trades]
    
    if not eligible:
        logger.warning(f"No symbols meet min_trades={min_trades} threshold")
        return []
    
    # Calculate composite scores
    scored = []
    for m in eligible:
        score = calculate_composite_score(m, weights)
        scored.append({**m, "composite_score": score})
    
    # Sort by score descending and take top-K
    scored.sort(key=lambda x: x["composite_score"], reverse=True)
    top_symbols = scored[:top_k]
    
    logger.info(f"Selected {len(top_symbols)} symbols from {len(eligible)} eligible candidates")
    for i, s in enumerate(top_symbols, 1):
        logger.info(
            f"  #{i} {s['symbol']}_{s['tf']}: score={s['composite_score']:.3f} "
            f"sharpe={s.get('sharpe', 0):.2f} pf={s.get('profit_factor', 0):.2f} "
            f"dd={s.get('max_drawdown', 0):.1f}% trades={s.get('trades', 0)}"
        )
    
    return top_symbols


def calculate_composite_score(
    metrics: Dict[str, Any],
    weights: Dict[str, float]
) -> float:
    """
    Calculate composite score for a single symbol/tf.
    
    Formula:
        score = w_sharpe*norm(sharpe) + w_pf*norm(profit_factor) 
                - w_dd*norm(max_drawdown) + w_wr*norm(winrate)
    """
    sharpe = metrics.get("sharpe", 0.0)
    pf = metrics.get("profit_factor", 0.0)
    dd = metrics.get("max_drawdown", 0.0)
    wr = metrics.get("winrate", 0.0)
    
    # Normalize using robust scaling (clamp to reasonable ranges)
    norm_sharpe = normalize_metric(sharpe, min_val=-2.0, max_val=5.0)
    norm_pf = normalize_metric(pf, min_val=0.0, max_val=3.0)
    norm_dd = normalize_metric(dd, min_val=0.0, max_val=50.0)  # lower is better
    norm_wr = normalize_metric(wr, min_val=30.0, max_val=70.0)
    
    # Composite score (note: drawdown is subtracted since lower is better)
    score = (
        weights.get("sharpe", 0.0) * norm_sharpe +
        weights.get("profit_factor", 0.0) * norm_pf -
        weights.get("max_drawdown", 0.0) * norm_dd +
        weights.get("winrate", 0.0) * norm_wr
    )
    
    return float(score)


def normalize_metric(value: float, min_val: float, max_val: float) -> float:
    """
    Normalize metric to [0, 1] range with clamping.
    
    Args:
        value: Raw metric value
        min_val: Minimum expected value (maps to 0)
        max_val: Maximum expected value (maps to 1)
    
    Returns:
        Normalized value clamped to [0, 1]
    """
    if max_val <= min_val:
        return 0.5
    
    normalized = (value - min_val) / (max_val - min_val)
    return float(np.clip(normalized, 0.0, 1.0))


def aggregate_by_symbol(
    metrics_list: List[Dict[str, Any]],
    aggregation: str = "best"
) -> List[Dict[str, Any]]:
    """
    Aggregate metrics across timeframes for each symbol.
    
    Args:
        metrics_list: List of metrics dicts
        aggregation: Method - 'best' (take best tf per symbol) or 'avg' (average across tfs)
    
    Returns:
        List with one entry per symbol
    """
    by_symbol: Dict[str, List[Dict]] = {}
    for m in metrics_list:
        sym = m.get("symbol", "")
        if sym not in by_symbol:
            by_symbol[sym] = []
        by_symbol[sym].append(m)
    
    aggregated = []
    for sym, tfs in by_symbol.items():
        if aggregation == "best":
            # Take the timeframe with best composite score
            best = max(tfs, key=lambda x: calculate_composite_score(x, {}))
            aggregated.append(best)
        elif aggregation == "avg":
            # Average metrics across timeframes
            avg_metrics = _average_metrics(tfs)
            aggregated.append(avg_metrics)
        else:
            logger.warning(f"Unknown aggregation method: {aggregation}, using 'best'")
            best = max(tfs, key=lambda x: calculate_composite_score(x, {}))
            aggregated.append(best)
    
    return aggregated


def _average_metrics(metrics_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Average numeric metrics across a list of metric dicts."""
    if not metrics_list:
        return {}
    
    numeric_keys = ["sharpe", "profit_factor", "max_drawdown", "winrate", "trades", "total_return"]
    averaged = {"symbol": metrics_list[0].get("symbol", ""), "tf": "aggregated"}
    
    for key in numeric_keys:
        values = [m.get(key, 0.0) for m in metrics_list]
        averaged[key] = float(np.mean(values))
    
    return averaged
