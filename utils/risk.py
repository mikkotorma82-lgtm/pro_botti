"""
Risk management utilities
"""
import numpy as np
from typing import Dict, Any, Tuple


def calculate_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    """
    Calculate performance metrics
    
    Args:
        y_true: True labels
        y_pred: Predicted labels
    
    Returns:
        Dict with metrics
    """
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
    
    metrics = {
        'accuracy': float(accuracy_score(y_true, y_pred)),
        'precision': float(precision_score(y_true, y_pred, zero_division=0)),
        'recall': float(recall_score(y_true, y_pred, zero_division=0)),
        'f1': float(f1_score(y_true, y_pred, zero_division=0))
    }
    
    # Win rate (for trading)
    if len(y_pred) > 0:
        metrics['win_rate'] = float(np.sum(y_pred == 1) / len(y_pred))
    else:
        metrics['win_rate'] = 0.0
    
    return metrics


def check_risk_limits(symbol: str, decision: str, config: Dict[str, Any]) -> bool:
    """
    Check if trade passes risk management rules
    
    Args:
        symbol: Trading symbol
        decision: 'BUY' or 'SELL'
        config: Configuration dict
    
    Returns:
        True if trade is allowed
    """
    risk_config = config.get('risk', {})
    
    # TODO: Implement actual position tracking
    # For now, always allow in paper trading mode
    
    max_position = risk_config.get('max_position_size_usdt', 1000)
    max_drawdown = risk_config.get('max_drawdown_pct', 20)
    
    # Placeholder checks
    current_positions = 0  # TODO: Get from position tracker
    
    if current_positions >= 5:  # Max 5 concurrent positions
        print(f"⚠️  Max positions reached ({current_positions})")
        return False
    
    return True


def calculate_position_metrics(entry_price: float, current_price: float, position_size: float) -> Dict[str, float]:
    """
    Calculate position metrics
    
    Args:
        entry_price: Entry price
        current_price: Current market price
        position_size: Position size
    
    Returns:
        Dict with PnL metrics
    """
    pnl = (current_price - entry_price) * position_size
    pnl_pct = ((current_price - entry_price) / entry_price) * 100
    
    return {
        'pnl': pnl,
        'pnl_pct': pnl_pct,
        'entry_price': entry_price,
        'current_price': current_price,
        'position_size': position_size
    }


def calculate_stop_loss(entry_price: float, direction: str, atr: float = None, pct: float = 5.0) -> float:
    """
    Calculate stop loss level
    
    Args:
        entry_price: Entry price
        direction: 'BUY' or 'SELL'
        atr: Average True Range (optional, for dynamic stops)
        pct: Stop loss percentage (fallback)
    
    Returns:
        Stop loss price
    """
    if atr:
        # ATR-based stop loss (2x ATR)
        stop_distance = 2 * atr
    else:
        # Percentage-based stop loss
        stop_distance = entry_price * (pct / 100)
    
    if direction == 'BUY':
        return entry_price - stop_distance
    else:
        return entry_price + stop_distance


def calculate_take_profit(entry_price: float, direction: str, risk_reward_ratio: float = 2.0, stop_loss: float = None) -> float:
    """
    Calculate take profit level
    
    Args:
        entry_price: Entry price
        direction: 'BUY' or 'SELL'
        risk_reward_ratio: Risk/reward ratio
        stop_loss: Stop loss level (for calculating distance)
    
    Returns:
        Take profit price
    """
    if stop_loss:
        # Calculate TP based on risk/reward ratio
        stop_distance = abs(entry_price - stop_loss)
        tp_distance = stop_distance * risk_reward_ratio
    else:
        # Default 10% take profit
        tp_distance = entry_price * 0.10
    
    if direction == 'BUY':
        return entry_price + tp_distance
    else:
        return entry_price - tp_distance


def calculate_max_drawdown(equity_curve: np.ndarray) -> float:
    """
    Calculate maximum drawdown from equity curve
    
    Args:
        equity_curve: Array of equity values over time
    
    Returns:
        Maximum drawdown as percentage
    """
    if len(equity_curve) == 0:
        return 0.0
    
    peak = np.maximum.accumulate(equity_curve)
    drawdown = (equity_curve - peak) / peak
    max_dd = np.min(drawdown) * 100  # Convert to percentage
    
    return abs(max_dd)


def calculate_sharpe_ratio(returns: np.ndarray, risk_free_rate: float = 0.02) -> float:
    """
    Calculate Sharpe ratio
    
    Args:
        returns: Array of returns
        risk_free_rate: Annual risk-free rate
    
    Returns:
        Sharpe ratio
    """
    if len(returns) == 0 or np.std(returns) == 0:
        return 0.0
    
    excess_returns = returns - (risk_free_rate / 252)  # Daily risk-free rate
    sharpe = np.mean(excess_returns) / np.std(excess_returns)
    
    # Annualize (assuming daily returns)
    sharpe_annual = sharpe * np.sqrt(252)
    
    return sharpe_annual


if __name__ == '__main__':
    # Test risk calculations
    print("Testing risk management...")
    
    # Test stop loss calculation
    entry = 50000
    sl = calculate_stop_loss(entry, 'BUY', pct=5.0)
    tp = calculate_take_profit(entry, 'BUY', risk_reward_ratio=2.0, stop_loss=sl)
    
    print(f"Entry: ${entry}")
    print(f"Stop Loss: ${sl:.2f} ({((sl - entry) / entry * 100):.2f}%)")
    print(f"Take Profit: ${tp:.2f} ({((tp - entry) / entry * 100):.2f}%)")
    
    # Test drawdown
    equity = np.array([10000, 10500, 10200, 9800, 10300, 11000])
    dd = calculate_max_drawdown(equity)
    print(f"\nMax Drawdown: {dd:.2f}%")
    
    print("\n✅ Risk management tests complete")
