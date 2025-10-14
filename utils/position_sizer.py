"""
Position sizing utilities
"""
from typing import Dict, Any


def calculate_position_size(
    symbol: str,
    decision: str,
    config: Dict[str, Any],
    current_price: float,
    account_balance: float = None,
    volatility: float = None
) -> float:
    """
    Calculate appropriate position size based on risk parameters
    
    Args:
        symbol: Trading symbol
        decision: 'BUY' or 'SELL'
        config: Configuration dict
        current_price: Current market price
        account_balance: Account balance (if None, uses config max)
        volatility: Current volatility measure
    
    Returns:
        Position size (in base currency units)
    """
    risk_config = config.get('risk', {})
    
    # Get max position size in USDT
    max_position_usdt = risk_config.get('max_position_size_usdt', 1000)
    
    # Get leverage
    leverage = risk_config.get('max_leverage', 1)
    
    # Base position size
    position_value_usdt = max_position_usdt
    
    # Adjust for account balance if provided
    if account_balance:
        # Use a fixed percentage of account (e.g., 10%)
        account_risk_pct = risk_config.get('account_risk_pct', 10.0)
        position_from_account = account_balance * (account_risk_pct / 100)
        position_value_usdt = min(position_value_usdt, position_from_account)
    
    # Adjust for volatility if provided
    if volatility:
        # Reduce position size in high volatility
        # If volatility > 2%, reduce position proportionally
        vol_threshold = 0.02  # 2%
        if volatility > vol_threshold:
            vol_factor = vol_threshold / volatility
            position_value_usdt *= vol_factor
    
    # Calculate position size in base currency
    position_size = (position_value_usdt * leverage) / current_price
    
    # Round to reasonable precision
    if current_price > 1000:
        # For expensive assets (BTC, etc), use 6 decimals
        position_size = round(position_size, 6)
    else:
        # For cheaper assets, use 2 decimals
        position_size = round(position_size, 2)
    
    return position_size


def adjust_for_existing_positions(
    position_size: float,
    existing_positions: int,
    max_positions: int = 5
) -> float:
    """
    Adjust position size based on existing positions
    
    Args:
        position_size: Calculated position size
        existing_positions: Number of existing open positions
        max_positions: Maximum allowed concurrent positions
    
    Returns:
        Adjusted position size
    """
    if existing_positions >= max_positions:
        return 0.0
    
    # Reduce position size as we approach max positions
    available_slots = max_positions - existing_positions
    adjustment_factor = available_slots / max_positions
    
    return position_size * adjustment_factor


def calculate_kelly_criterion(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    max_kelly: float = 0.25
) -> float:
    """
    Calculate Kelly Criterion for position sizing
    
    Args:
        win_rate: Historical win rate (0-1)
        avg_win: Average winning trade size
        avg_loss: Average losing trade size
        max_kelly: Maximum Kelly fraction (for safety)
    
    Returns:
        Kelly fraction (portion of capital to risk)
    """
    if avg_loss == 0 or win_rate == 0 or win_rate == 1:
        return 0.0
    
    # Kelly formula: f* = (p * b - q) / b
    # where p = win_rate, q = 1 - p, b = avg_win/avg_loss
    b = avg_win / avg_loss
    kelly = (win_rate * b - (1 - win_rate)) / b
    
    # Limit to max Kelly for safety
    kelly = max(0, min(kelly, max_kelly))
    
    return kelly


if __name__ == '__main__':
    # Test position sizing
    print("Testing position sizing...")
    
    config = {
        'risk': {
            'max_position_size_usdt': 1000,
            'max_leverage': 1,
            'account_risk_pct': 10.0
        }
    }
    
    # Test 1: Basic position size
    price = 50000
    size = calculate_position_size('BTCUSDT', 'BUY', config, price)
    print(f"\nBasic position size at ${price}: {size:.6f} BTC")
    print(f"Position value: ${size * price:.2f}")
    
    # Test 2: With volatility adjustment
    size_vol = calculate_position_size('BTCUSDT', 'BUY', config, price, volatility=0.05)
    print(f"\nWith high volatility (5%): {size_vol:.6f} BTC")
    print(f"Position value: ${size_vol * price:.2f}")
    
    # Test 3: Kelly criterion
    kelly = calculate_kelly_criterion(
        win_rate=0.55,
        avg_win=150,
        avg_loss=100,
        max_kelly=0.25
    )
    print(f"\nKelly fraction: {kelly:.3f} ({kelly * 100:.1f}% of capital)")
    
    print("\n✅ Position sizing tests complete")
