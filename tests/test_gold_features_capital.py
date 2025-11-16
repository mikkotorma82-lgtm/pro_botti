"""
Tests for gold_features_capital.py
"""

import sys
import os
import pytest
from unittest.mock import Mock, MagicMock
import pandas as pd
import numpy as np

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.gold_features_capital import build_gold_dataset_capital


class MockCapitalClient:
    """Mock Capital.com client for testing."""
    
    def __init__(self, n_candles=200):
        self.n_candles = n_candles
    
    def get_candles(self, epic, resolution="HOUR", max=200, from_ts=None, to_ts=None):
        """Return mock candle data."""
        # Generate synthetic price data
        np.random.seed(42)
        
        # Start with base price around 1800 for gold
        base_price = 1800
        returns = np.random.randn(self.n_candles) * 0.01  # 1% volatility
        prices = base_price * np.exp(np.cumsum(returns))
        
        candles = []
        for i in range(self.n_candles):
            # Generate OHLC with some randomness
            close = prices[i]
            high = close * (1 + abs(np.random.randn() * 0.005))
            low = close * (1 - abs(np.random.randn() * 0.005))
            open_price = close + np.random.randn() * (high - low) * 0.3
            
            candle = {
                "snapshotTime": f"2024-01-{(i % 30) + 1:02d}T{i % 24:02d}:00:00",
                "openPrice": open_price,
                "highPrice": high,
                "lowPrice": low,
                "closePrice": close,
            }
            candles.append(candle)
        
        return candles


def test_build_gold_dataset_capital_signature():
    """Test that build_gold_dataset_capital accepts all required parameters without error."""
    client = MockCapitalClient(n_candles=100)
    
    # This should not raise TypeError
    X, y_dir, y_mag = build_gold_dataset_capital(
        client,
        gold_symbol="XAUUSD",
        macro_epics=None,
        base_tf="15m",
        start=None,
        end=None,
        horizon_bars=8,
        use_full_history=True,
        min_move_atr=0.1,
        min_move_pct=0.0005,
    )
    
    assert isinstance(X, pd.DataFrame), "X should be a DataFrame"
    assert isinstance(y_dir, pd.Series), "y_dir should be a Series"
    assert isinstance(y_mag, pd.Series), "y_mag should be a Series"
    assert len(X) == len(y_dir) == len(y_mag), "All outputs should have same length"


def test_build_gold_dataset_capital_use_full_history_false():
    """Test build_gold_dataset_capital with use_full_history=False."""
    client = MockCapitalClient(n_candles=100)
    
    X, y_dir, y_mag = build_gold_dataset_capital(
        client,
        gold_symbol="XAUUSD",
        use_full_history=False,
        min_move_atr=0.1,
        min_move_pct=0.0005,
    )
    
    assert len(X) > 0, "Should return data with use_full_history=False"


def test_min_move_atr_affects_valid_move():
    """Test that min_move_atr parameter affects the valid_move mask."""
    client = MockCapitalClient(n_candles=100)
    
    # Get results with strict threshold
    X1, y_dir1, y_mag1 = build_gold_dataset_capital(
        client,
        gold_symbol="XAUUSD",
        min_move_atr=0.5,  # High threshold - fewer valid moves
        min_move_pct=0.01,  # High percentage
        horizon_bars=8,
    )
    
    # Get results with lenient threshold
    X2, y_dir2, y_mag2 = build_gold_dataset_capital(
        client,
        gold_symbol="XAUUSD",
        min_move_atr=0.05,  # Low threshold - more valid moves
        min_move_pct=0.0001,  # Low percentage
        horizon_bars=8,
    )
    
    # Count non-zero directional labels (valid moves)
    valid_moves_strict = (y_dir1 != 0).sum()
    valid_moves_lenient = (y_dir2 != 0).sum()
    
    # Lenient threshold should produce more or equal valid moves
    assert valid_moves_lenient >= valid_moves_strict, \
        f"Lenient threshold should produce more valid moves: {valid_moves_lenient} >= {valid_moves_strict}"


def test_min_move_pct_affects_valid_move():
    """Test that min_move_pct parameter affects the valid_move mask."""
    client = MockCapitalClient(n_candles=100)
    
    # Get results with strict percentage threshold
    X1, y_dir1, y_mag1 = build_gold_dataset_capital(
        client,
        gold_symbol="XAUUSD",
        min_move_atr=0.05,
        min_move_pct=0.02,  # High percentage - fewer valid moves
        horizon_bars=8,
    )
    
    # Get results with lenient percentage threshold
    X2, y_dir2, y_mag2 = build_gold_dataset_capital(
        client,
        gold_symbol="XAUUSD",
        min_move_atr=0.05,
        min_move_pct=0.0001,  # Low percentage - more valid moves
        horizon_bars=8,
    )
    
    # Count non-zero directional labels
    valid_moves_strict = (y_dir1 != 0).sum()
    valid_moves_lenient = (y_dir2 != 0).sum()
    
    # Lenient should have more or equal valid moves
    assert valid_moves_lenient >= valid_moves_strict, \
        f"Lenient pct threshold should produce more valid moves: {valid_moves_lenient} >= {valid_moves_strict}"


def test_features_engineered():
    """Test that expected features are engineered."""
    client = MockCapitalClient(n_candles=100)
    
    X, y_dir, y_mag = build_gold_dataset_capital(
        client,
        gold_symbol="XAUUSD",
        min_move_atr=0.1,
        min_move_pct=0.0005,
    )
    
    # Check for expected feature columns
    expected_features = ["return", "atr", "rsi", "macd", "macd_signal", "macd_hist"]
    
    for feature in expected_features:
        assert feature in X.columns, f"Feature {feature} should be in X"
    
    # Check for SMA-derived features
    sma_features = [col for col in X.columns if "close_vs_sma" in col]
    assert len(sma_features) > 0, "Should have close_vs_sma features"


def test_directional_labels():
    """Test that directional labels are -1, 0, or 1."""
    client = MockCapitalClient(n_candles=100)
    
    X, y_dir, y_mag = build_gold_dataset_capital(
        client,
        gold_symbol="XAUUSD",
        min_move_atr=0.1,
        min_move_pct=0.0005,
    )
    
    unique_labels = set(y_dir.unique())
    valid_labels = {-1, 0, 1}
    
    assert unique_labels.issubset(valid_labels), \
        f"Directional labels should be subset of {valid_labels}, got {unique_labels}"


def test_magnitude_labels_non_negative():
    """Test that magnitude labels are non-negative."""
    client = MockCapitalClient(n_candles=100)
    
    X, y_dir, y_mag = build_gold_dataset_capital(
        client,
        gold_symbol="XAUUSD",
        min_move_atr=0.1,
        min_move_pct=0.0005,
    )
    
    assert (y_mag >= 0).all(), "Magnitude labels should be non-negative"


def test_no_nan_in_output():
    """Test that output data has no NaN values."""
    client = MockCapitalClient(n_candles=100)
    
    X, y_dir, y_mag = build_gold_dataset_capital(
        client,
        gold_symbol="XAUUSD",
        min_move_atr=0.1,
        min_move_pct=0.0005,
    )
    
    assert not X.isna().any().any(), "X should not contain NaN values"
    assert not y_dir.isna().any(), "y_dir should not contain NaN values"
    assert not y_mag.isna().any(), "y_mag should not contain NaN values"


def test_macro_epics_parameter():
    """Test that macro_epics parameter is accepted."""
    client = MockCapitalClient(n_candles=100)
    
    macro_epics = {
        "DXY": "US_DOLLAR_INDEX",
        "SPX": "US500",
    }
    
    # Should not raise error
    X, y_dir, y_mag = build_gold_dataset_capital(
        client,
        gold_symbol="XAUUSD",
        macro_epics=macro_epics,
        min_move_atr=0.1,
        min_move_pct=0.0005,
    )
    
    assert len(X) > 0, "Should return data with macro_epics"


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
