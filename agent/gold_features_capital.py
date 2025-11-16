"""
Gold feature engineering for Capital.com data.
"""

from typing import Dict, Optional, Tuple
import pandas as pd
import numpy as np
from tools.capital_client import CapitalClient


def build_gold_dataset_capital(
    client: CapitalClient,
    gold_symbol: str = "XAUUSD",
    macro_epics: Optional[Dict[str, str]] = None,
    base_tf: str = "15m",
    start: Optional[str] = None,
    end: Optional[str] = None,
    horizon_bars: int = 8,
    use_full_history: bool = True,
    min_move_atr: float = 0.1,
    min_move_pct: float = 0.0005,
) -> Tuple[pd.DataFrame, pd.Series, pd.Series]:
    """
    Build a gold trading dataset from Capital.com.
    
    This function fetches historical price data for gold and optionally macro indicators,
    engineers features, and creates labeled targets for direction and magnitude prediction.
    
    Args:
        client: Capital.com API client instance
        gold_symbol: Symbol for gold (e.g., "XAUUSD")
        macro_epics: Optional dict of macro indicator names to their Capital.com epics
        base_tf: Base timeframe for data (e.g., "15m", "1h", "4h")
        start: Optional start date for data (ISO format). If None and use_full_history=True,
               fetches maximum available history
        end: Optional end date for data (ISO format)
        horizon_bars: Number of bars to look ahead for target labels
        use_full_history: If True, load maximum available history from Capital.com when
                         start is None. If False, uses default lookback
        min_move_atr: Minimum move in ATR units to treat as a valid signal.
                     Used to filter out small moves that may not be tradeable
        min_move_pct: Minimum move in percentage terms to treat as a valid signal.
                     Used to filter out small moves that may not be tradeable
    
    Returns:
        Tuple of (X, y_dir, y_mag) where:
            X: DataFrame of features
            y_dir: Series of directional labels (1=up, -1=down, 0=neutral)
            y_mag: Series of magnitude labels (absolute return over horizon)
    
    Examples:
        >>> from tools.capital_client import CapitalClient
        >>> client = CapitalClient()
        >>> X, y_dir, y_mag = build_gold_dataset_capital(
        ...     client,
        ...     gold_symbol="XAUUSD",
        ...     base_tf="15m",
        ...     horizon_bars=8,
        ...     use_full_history=True,
        ...     min_move_atr=0.1,
        ...     min_move_pct=0.0005
        ... )
    """
    # Map timeframe strings to Capital.com resolution codes
    tf_mapping = {
        "1m": "MINUTE",
        "5m": "MINUTE_5",
        "15m": "MINUTE_15",
        "30m": "MINUTE_30",
        "1h": "HOUR",
        "4h": "HOUR_4",
        "1d": "DAY",
    }
    
    resolution = tf_mapping.get(base_tf, "MINUTE_15")
    
    # Determine max candles to fetch based on use_full_history
    max_candles = 1000 if use_full_history else 500
    
    # Fetch gold price data using client's epic resolution
    epic = client._resolve_epic(gold_symbol)
    
    candles = client.get_candles(
        epic=epic,
        resolution=resolution,
        max=max_candles,
        from_ts=start,
        to_ts=end
    )
    
    if not candles:
        raise ValueError(f"No data returned for {gold_symbol} ({epic})")
    
    # Convert to DataFrame
    df = pd.DataFrame(candles)
    
    # Expected fields from Capital.com API: snapshotTime, openPrice, highPrice, lowPrice, closePrice
    # Rename to standard OHLC format
    if "snapshotTime" in df.columns:
        df["timestamp"] = pd.to_datetime(df["snapshotTime"])
    if "openPrice" in df.columns:
        df = df.rename(columns={
            "openPrice": "open",
            "highPrice": "high",
            "lowPrice": "low",
            "closePrice": "close"
        })
    
    df = df.set_index("timestamp").sort_index()
    
    # Feature engineering
    # 1. Returns
    df["return"] = df["close"].pct_change()
    
    # 2. Simple moving averages
    for period in [10, 20, 50]:
        df[f"sma_{period}"] = df["close"].rolling(period).mean()
        df[f"close_vs_sma_{period}"] = df["close"] / df[f"sma_{period}"] - 1
    
    # 3. Volatility (ATR approximation)
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr"] = true_range.rolling(14).mean()
    
    # 4. RSI
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))
    
    # 5. MACD
    ema_12 = df["close"].ewm(span=12).mean()
    ema_26 = df["close"].ewm(span=26).mean()
    df["macd"] = ema_12 - ema_26
    df["macd_signal"] = df["macd"].ewm(span=9).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]
    
    # Fetch and merge macro data if provided
    if macro_epics:
        for name, macro_epic in macro_epics.items():
            try:
                macro_candles = client.get_candles(
                    epic=macro_epic,
                    resolution=resolution,
                    max=max_candles,
                    from_ts=start,
                    to_ts=end
                )
                if macro_candles:
                    macro_df = pd.DataFrame(macro_candles)
                    if "snapshotTime" in macro_df.columns:
                        macro_df["timestamp"] = pd.to_datetime(macro_df["snapshotTime"])
                    if "closePrice" in macro_df.columns:
                        macro_df = macro_df.rename(columns={"closePrice": f"macro_{name}"})
                    macro_df = macro_df.set_index("timestamp")[[f"macro_{name}"]]
                    df = df.join(macro_df, how="left")
                    df[f"macro_{name}"] = df[f"macro_{name}"].ffill()
            except Exception as e:
                print(f"Warning: Could not fetch macro data for {name}: {e}")
    
    # Create target labels
    # Direction: sign of future return over horizon_bars
    future_return = df["close"].shift(-horizon_bars) / df["close"] - 1
    
    # Calculate return in ATR units and percentage
    ret_atr = future_return / (df["atr"] / df["close"])
    ret_pct = future_return.abs()
    
    # Valid move: either exceeds ATR threshold or percentage threshold
    valid_move = (ret_atr.abs() >= min_move_atr) | (ret_pct >= min_move_pct)
    
    # Direction labels: 1=up, -1=down, 0=neutral/small move
    y_dir = pd.Series(0, index=df.index)
    y_dir[valid_move & (future_return > 0)] = 1
    y_dir[valid_move & (future_return < 0)] = -1
    
    # Magnitude labels: absolute return
    y_mag = future_return.abs()
    
    # Features: drop intermediate columns, keep engineered features
    feature_cols = [col for col in df.columns if not col.startswith("sma_") or col.startswith("close_vs_")]
    feature_cols = [col for col in feature_cols if col not in ["open", "high", "low", "close"]]
    
    X = df[feature_cols].copy()
    
    # Drop rows with NaN (from rolling windows and future labels)
    valid_idx = ~(X.isna().any(axis=1) | y_dir.isna() | y_mag.isna())
    X = X[valid_idx]
    y_dir = y_dir[valid_idx]
    y_mag = y_mag[valid_idx]
    
    return X, y_dir, y_mag
