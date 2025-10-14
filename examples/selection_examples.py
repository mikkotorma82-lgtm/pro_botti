#!/usr/bin/env python3
"""
Example usage of the top-5 symbol selection system.
Demonstrates evaluation, selection, and monitoring workflows.
"""

import json
import numpy as np
from pathlib import Path
from datetime import datetime

# Add parent to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.metrics import calculate_metrics
from utils.selector import select_top_symbols, calculate_composite_score
from utils.position_watcher import create_position_watcher


def example_metrics_calculation():
    """Example: Calculate trading metrics from returns."""
    print("=" * 60)
    print("EXAMPLE 1: Metrics Calculation")
    print("=" * 60)
    print()
    
    # Simulate trading returns
    np.random.seed(42)
    returns = np.random.normal(0.001, 0.02, 100)  # 100 trades
    signals = np.random.choice([-1, 0, 1], 100)
    
    # Calculate metrics
    metrics = calculate_metrics(returns, signals)
    
    print("Trading Metrics:")
    print(f"  Trades: {metrics['trades']}")
    print(f"  Win Rate: {metrics['winrate']:.1f}%")
    print(f"  Profit Factor: {metrics['profit_factor']:.2f}")
    print(f"  Sharpe Ratio: {metrics['sharpe']:.2f}")
    print(f"  Sortino Ratio: {metrics['sortino']:.2f}")
    print(f"  Max Drawdown: {metrics['max_drawdown']:.1f}%")
    print(f"  Avg Trade Return: {metrics['avg_trade_return']:.4f}")
    print(f"  Exposure: {metrics['exposure']:.1f}%")
    print()


def example_symbol_selection():
    """Example: Select top symbols from metrics."""
    print("=" * 60)
    print("EXAMPLE 2: Symbol Selection")
    print("=" * 60)
    print()
    
    # Sample metrics for multiple symbols
    metrics_list = [
        {
            "symbol": "US500", "tf": "1h",
            "sharpe": 1.8, "profit_factor": 2.3,
            "max_drawdown": 12.5, "winrate": 58.0,
            "trades": 120
        },
        {
            "symbol": "BTCUSDT", "tf": "1h",
            "sharpe": 2.2, "profit_factor": 2.8,
            "max_drawdown": 18.3, "winrate": 62.0,
            "trades": 95
        },
        {
            "symbol": "EURUSD", "tf": "1h",
            "sharpe": 1.2, "profit_factor": 1.8,
            "max_drawdown": 8.2, "winrate": 54.0,
            "trades": 140
        },
        {
            "symbol": "GBPUSD", "tf": "1h",
            "sharpe": 0.9, "profit_factor": 1.5,
            "max_drawdown": 15.7, "winrate": 48.0,
            "trades": 85
        },
        {
            "symbol": "ETHUSDT", "tf": "1h",
            "sharpe": 1.9, "profit_factor": 2.5,
            "max_drawdown": 14.2, "winrate": 60.0,
            "trades": 110
        },
    ]
    
    print("Available Symbols:")
    for m in metrics_list:
        score = calculate_composite_score(m, {
            "sharpe": 0.5, "profit_factor": 0.3,
            "max_drawdown": 0.2, "winrate": 0.0
        })
        print(f"  {m['symbol']:10} - Sharpe: {m['sharpe']:.2f}, "
              f"PF: {m['profit_factor']:.2f}, Score: {score:.3f}")
    print()
    
    # Select top-3
    top_symbols = select_top_symbols(
        metrics_list,
        top_k=3,
        min_trades=50,
        weights={"sharpe": 0.5, "profit_factor": 0.3, "max_drawdown": 0.2, "winrate": 0.0}
    )
    
    print("Selected Top-3:")
    for i, s in enumerate(top_symbols, 1):
        print(f"  {i}. {s['symbol']} (score: {s['composite_score']:.3f})")
    print()


def example_custom_weights():
    """Example: Use custom weights for selection."""
    print("=" * 60)
    print("EXAMPLE 3: Custom Weights")
    print("=" * 60)
    print()
    
    metrics = {
        "symbol": "TEST", "tf": "1h",
        "sharpe": 1.5, "profit_factor": 2.0,
        "max_drawdown": 10.0, "winrate": 55.0,
        "trades": 100
    }
    
    # Different weight configurations
    weight_configs = [
        {"name": "Sharpe-focused", "weights": {"sharpe": 0.7, "profit_factor": 0.2, "max_drawdown": 0.1, "winrate": 0.0}},
        {"name": "Balanced", "weights": {"sharpe": 0.5, "profit_factor": 0.3, "max_drawdown": 0.2, "winrate": 0.0}},
        {"name": "Low-risk", "weights": {"sharpe": 0.3, "profit_factor": 0.2, "max_drawdown": 0.5, "winrate": 0.0}},
        {"name": "Win-rate", "weights": {"sharpe": 0.3, "profit_factor": 0.2, "max_drawdown": 0.1, "winrate": 0.4}},
    ]
    
    print("Symbol Metrics:")
    print(f"  Sharpe: {metrics['sharpe']:.2f}")
    print(f"  Profit Factor: {metrics['profit_factor']:.2f}")
    print(f"  Max Drawdown: {metrics['max_drawdown']:.1f}%")
    print(f"  Win Rate: {metrics['winrate']:.1f}%")
    print()
    
    print("Scores with Different Weights:")
    for cfg in weight_configs:
        score = calculate_composite_score(metrics, cfg["weights"])
        print(f"  {cfg['name']:15} → Score: {score:.3f}")
    print()


def example_position_watcher():
    """Example: Position monitoring."""
    print("=" * 60)
    print("EXAMPLE 4: Position Monitoring")
    print("=" * 60)
    print()
    
    # Mock broker with some positions
    class MockBroker:
        def __init__(self):
            self.positions = [
                {"symbol": "US500", "direction": "BUY", "openLevel": 5000.0, "unrealizedPL": 150.0},
                {"symbol": "OLDCOIN", "direction": "SELL", "openLevel": 30000.0, "unrealizedPL": -200.0},
            ]
        
        def open_positions(self):
            return self.positions
        
        def close_position(self, **kwargs):
            print(f"    → Would close position: {kwargs}")
    
    # Create watcher
    broker = MockBroker()
    watcher = create_position_watcher(broker, check_interval=30)
    
    # Active symbols list (OLDCOIN is not active anymore)
    active_symbols = ["US500", "BTCUSDT", "EURUSD"]
    
    print("Active symbols:", active_symbols)
    print(f"Open positions: {len(broker.positions)}")
    print()
    
    # Check positions
    result = watcher.check_and_manage_positions(active_symbols)
    
    print("Monitoring Results:")
    print(f"  Total positions: {result['open_count']}")
    print(f"  Managed: {result['managed']}")
    print(f"  Errors: {result['errors']}")
    if result.get('inactive_symbols'):
        print(f"  Inactive symbols with positions: {result['inactive_symbols']}")
    print()
    print("Note: OLDCOIN is not in active list but still managed!")
    print()


def example_state_file():
    """Example: Working with state/active_symbols.json."""
    print("=" * 60)
    print("EXAMPLE 5: State File Management")
    print("=" * 60)
    print()
    
    # Create sample state
    state = {
        "generated_at": datetime.now().isoformat(),
        "timeframes": ["1h", "4h"],
        "top_k": 5,
        "symbols": ["BTCUSDT", "ETHUSDT", "US500", "EURUSD", "AAPL"],
        "criteria": {
            "min_trades": 25,
            "weights": {
                "sharpe": 0.5,
                "profit_factor": 0.3,
                "max_drawdown": 0.2,
                "winrate": 0.0
            },
            "lookback_days": 365
        }
    }
    
    # Save to file (in memory example)
    state_json = json.dumps(state, indent=2)
    
    print("Active Symbols State:")
    print(state_json)
    print()
    
    # How to load in live trading
    print("In live trading, load with:")
    print("  state_file = Path('state/active_symbols.json')")
    print("  if state_file.exists():")
    print("      data = json.loads(state_file.read_text())")
    print("      symbols = data['symbols']")
    print()


def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("PRO BOTTI - TOP-5 SELECTION SYSTEM EXAMPLES")
    print("=" * 60)
    print()
    
    example_metrics_calculation()
    example_symbol_selection()
    example_custom_weights()
    example_position_watcher()
    example_state_file()
    
    print("=" * 60)
    print("All examples completed!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("  1. Run evaluation: python scripts/evaluate.py --timeframes 1h")
    print("  2. Select top-K: python -m cli select-top --tf 1h --top-k 5")
    print("  3. Show active: python -m cli show-active")
    print("  4. Run live: python -m cli live --config config.yaml")
    print()


if __name__ == "__main__":
    main()
