"""
Gold trading model training and backtesting for Capital.com.
"""

from typing import Optional, Dict
import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import TimeSeriesSplit
from tools.capital_client import CapitalClient
from agent.gold_features_capital import build_gold_dataset_capital


def train_and_backtest(
    client: CapitalClient,
    cfg: object,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Dict:
    """
    Train a gold trading model and perform walk-forward backtesting.
    
    Args:
        client: Capital.com API client
        cfg: Configuration object with attributes:
            - gold_symbol: str
            - macro_epics: Optional[Dict[str, str]]
            - base_tf: str
            - horizon_bars: int
            - use_full_history: bool
            - min_move_atr: float
            - min_move_pct: float
        start: Optional start date for training data
        end: Optional end date for training data
    
    Returns:
        Dictionary with training results and metrics
    """
    # Build dataset using the updated signature
    X, y_dir, y_mag = build_gold_dataset_capital(
        client,
        gold_symbol=cfg.gold_symbol,
        macro_epics=cfg.macro_epics,
        base_tf=cfg.base_tf,
        start=start,
        end=end,
        horizon_bars=cfg.horizon_bars,
        use_full_history=cfg.use_full_history,
        min_move_atr=cfg.min_move_atr,
        min_move_pct=cfg.min_move_pct,
    )
    
    # Convert directional labels to binary (long/short)
    # 1 = long (positive), 0 = short/neutral (negative or zero)
    y_binary = (y_dir > 0).astype(int)
    
    # Walk-forward cross-validation
    tscv = TimeSeriesSplit(n_splits=5)
    
    results = {
        "n_samples": len(X),
        "n_features": X.shape[1],
        "n_long_signals": (y_dir > 0).sum(),
        "n_short_signals": (y_dir < 0).sum(),
        "n_neutral": (y_dir == 0).sum(),
        "fold_scores": []
    }
    
    for fold_idx, (train_idx, test_idx) in enumerate(tscv.split(X)):
        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y_binary.iloc[train_idx], y_binary.iloc[test_idx]
        
        # Train GBDT classifier
        model = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            random_state=42
        )
        model.fit(X_train, y_train)
        
        # Evaluate
        train_score = model.score(X_train, y_train)
        test_score = model.score(X_test, y_test)
        
        results["fold_scores"].append({
            "fold": fold_idx,
            "train_score": train_score,
            "test_score": test_score,
            "n_train": len(train_idx),
            "n_test": len(test_idx)
        })
    
    # Calculate average scores
    results["avg_train_score"] = np.mean([f["train_score"] for f in results["fold_scores"]])
    results["avg_test_score"] = np.mean([f["test_score"] for f in results["fold_scores"]])
    
    return results
