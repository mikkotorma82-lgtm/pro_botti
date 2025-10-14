"""
Feature engineering utilities
"""
import pandas as pd
import numpy as np


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build technical indicators and features from OHLCV data
    
    Args:
        df: DataFrame with columns: time, open, high, low, close, volume
    
    Returns:
        DataFrame with additional feature columns
    """
    df = df.copy()
    
    # Returns
    df['returns'] = df['close'].pct_change()
    df['log_returns'] = np.log(df['close'] / df['close'].shift(1))
    
    # Volume features
    df['volume_ma'] = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_ma']
    
    # Price ranges
    df['high_low_ratio'] = df['high'] / df['low']
    df['close_open_ratio'] = df['close'] / df['open']
    
    # Moving averages
    df['ema_fast'] = df['close'].ewm(span=12, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=26, adjust=False).mean()
    df['ema_signal'] = (df['ema_fast'] - df['ema_slow']) / df['ema_slow']
    
    df['sma_20'] = df['close'].rolling(20).mean()
    df['sma_50'] = df['close'].rolling(50).mean()
    df['sma_200'] = df['close'].rolling(200).mean()
    
    # RSI
    df['rsi'] = calculate_rsi(df['close'], periods=14)
    
    # MACD
    df['macd'], df['macd_signal'], df['macd_hist'] = calculate_macd(df['close'])
    
    # Bollinger Bands
    df['bb_upper'], df['bb_middle'], df['bb_lower'] = calculate_bollinger_bands(df['close'])
    df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
    df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
    
    # ATR (Average True Range)
    df['atr'] = calculate_atr(df, periods=14)
    
    # Momentum
    df['momentum'] = df['close'] - df['close'].shift(10)
    df['roc'] = ((df['close'] - df['close'].shift(10)) / df['close'].shift(10)) * 100
    
    # Volatility
    df['volatility'] = df['returns'].rolling(20).std()
    
    return df


def calculate_rsi(series: pd.Series, periods: int = 14) -> pd.Series:
    """Calculate Relative Strength Index"""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=periods).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=periods).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def calculate_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """Calculate MACD indicator"""
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    
    macd = ema_fast - ema_slow
    macd_signal = macd.ewm(span=signal, adjust=False).mean()
    macd_hist = macd - macd_signal
    
    return macd, macd_signal, macd_hist


def calculate_bollinger_bands(series: pd.Series, periods: int = 20, std_dev: float = 2.0):
    """Calculate Bollinger Bands"""
    middle = series.rolling(window=periods).mean()
    std = series.rolling(window=periods).std()
    
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    
    return upper, middle, lower


def calculate_atr(df: pd.DataFrame, periods: int = 14) -> pd.Series:
    """Calculate Average True Range"""
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = true_range.rolling(window=periods).mean()
    
    return atr


if __name__ == '__main__':
    # Test feature building
    print("Testing feature engineering...")
    
    # Create sample data
    dates = pd.date_range(start='2023-01-01', periods=100, freq='1h')
    df = pd.DataFrame({
        'time': dates,
        'open': np.random.randn(100).cumsum() + 100,
        'high': np.random.randn(100).cumsum() + 102,
        'low': np.random.randn(100).cumsum() + 98,
        'close': np.random.randn(100).cumsum() + 100,
        'volume': np.random.randint(1000, 10000, 100)
    })
    
    df_features = build_features(df)
    print(f"✅ Built {len(df_features.columns)} features")
    print(f"Feature columns: {list(df_features.columns)}")
