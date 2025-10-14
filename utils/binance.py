"""
Binance exchange utilities
"""
import os
from datetime import datetime, timedelta
from typing import Optional
import pandas as pd


def fetch_ohlcv(symbol: str, timeframe: str, since: Optional[datetime] = None, limit: int = 1000) -> Optional[pd.DataFrame]:
    """
    Fetch OHLCV data from Binance
    
    Args:
        symbol: Trading pair (e.g., 'BTCUSDT')
        timeframe: Candle timeframe (e.g., '15m', '1h', '4h')
        since: Start date for historical data
        limit: Maximum number of candles to fetch
    
    Returns:
        DataFrame with columns: time, open, high, low, close, volume
    """
    try:
        import ccxt
    except ImportError:
        print("❌ ccxt not installed. Run: pip install ccxt")
        return None
    
    try:
        exchange = ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY', ''),
            'secret': os.getenv('BINANCE_API_SECRET', ''),
            'enableRateLimit': True
        })
        
        # Convert timeframe format
        tf_map = {
            '15m': '15m',
            '1h': '1h',
            '4h': '4h',
            '1d': '1d'
        }
        ccxt_tf = tf_map.get(timeframe, timeframe)
        
        # Fetch data
        since_ms = int(since.timestamp() * 1000) if since else None
        
        all_candles = []
        current_since = since_ms
        
        while True:
            candles = exchange.fetch_ohlcv(
                symbol,
                timeframe=ccxt_tf,
                since=current_since,
                limit=min(limit, 1000)
            )
            
            if not candles:
                break
            
            all_candles.extend(candles)
            
            if len(candles) < 1000 or len(all_candles) >= limit:
                break
            
            # Update since to last candle time
            current_since = candles[-1][0] + 1
        
        if not all_candles:
            return None
        
        # Convert to DataFrame
        df = pd.DataFrame(all_candles, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df['time'] = pd.to_datetime(df['time'], unit='ms')
        
        return df
        
    except Exception as e:
        print(f"❌ Error fetching OHLCV for {symbol} {timeframe}: {e}")
        return None


def fetch_latest_candles(symbol: str, timeframe: str, limit: int = 200) -> Optional[pd.DataFrame]:
    """
    Fetch most recent candles from Binance
    
    Args:
        symbol: Trading pair
        timeframe: Candle timeframe
        limit: Number of candles to fetch
    
    Returns:
        DataFrame with recent candles
    """
    try:
        import ccxt
    except ImportError:
        print("❌ ccxt not installed")
        return None
    
    try:
        exchange = ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY', ''),
            'secret': os.getenv('BINANCE_API_SECRET', ''),
            'enableRateLimit': True
        })
        
        candles = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        
        if not candles:
            return None
        
        df = pd.DataFrame(candles, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df['time'] = pd.to_datetime(df['time'], unit='ms')
        
        return df
        
    except Exception as e:
        print(f"❌ Error fetching latest candles: {e}")
        return None


def place_order(symbol: str, side: str, order_type: str, quantity: float, price: Optional[float] = None) -> dict:
    """
    Place an order on Binance
    
    Args:
        symbol: Trading pair
        side: 'buy' or 'sell'
        order_type: 'market' or 'limit'
        quantity: Order quantity
        price: Limit price (required for limit orders)
    
    Returns:
        Order result dict
    """
    try:
        import ccxt
    except ImportError:
        return {'ok': False, 'error': 'ccxt not installed'}
    
    try:
        exchange = ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY', ''),
            'secret': os.getenv('BINANCE_API_SECRET', ''),
            'enableRateLimit': True
        })
        
        params = {}
        if order_type == 'limit' and price:
            order = exchange.create_limit_order(symbol, side, quantity, price, params)
        else:
            order = exchange.create_market_order(symbol, side, quantity, params)
        
        return {
            'ok': True,
            'order_id': order.get('id'),
            'symbol': symbol,
            'side': side,
            'type': order_type,
            'quantity': quantity,
            'price': price,
            'raw': order
        }
        
    except Exception as e:
        return {
            'ok': False,
            'error': str(e),
            'symbol': symbol,
            'side': side
        }


if __name__ == '__main__':
    # Test data fetch
    print("Testing Binance connection...")
    df = fetch_latest_candles('BTCUSDT', '1h', limit=10)
    if df is not None:
        print(f"✅ Fetched {len(df)} candles")
        print(df.tail())
    else:
        print("❌ Failed to fetch data")
