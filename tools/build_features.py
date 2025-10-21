import numpy as np
import pandas as pd

FEATURES = [
    "rsi14", "sma10", "sma20", "ema12", "ema26",
    "macd", "macd_signal", "macd_hist", "atr14"
]

def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        new_cols = []
        for tup in df.columns:
            parts = [p for p in tup if isinstance(p, str) and p != ""]
            name = parts[0] if parts else str(tup[0])
            new_cols.append(name.lower())
        df.columns = new_cols
    else:
        df.columns = [str(c).lower() for c in df.columns]
    return df

def _to_1d_series(x, index=None, dtype=float) -> pd.Series:
    arr = np.asarray(x)
    if arr.ndim == 2 and arr.shape[1] == 1:
        arr = arr[:, 0]
    elif arr.ndim != 1:
        raise ValueError(f"Expected 1D or (N,1), got {arr.shape}")
    return pd.Series(arr, index=index, dtype=dtype)

def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    s = series.astype(float)
    delta = s.diff()
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    roll_up = pd.Series(gain, index=s.index).ewm(alpha=1/period, adjust=False).mean()
    roll_down = pd.Series(loss, index=s.index).ewm(alpha=1/period, adjust=False).mean()
    rs = roll_up / (roll_down.replace(0, np.nan))
    return (100 - (100 / (1 + rs))).bfill()

def _atr(high, low, close, period: int = 14) -> pd.Series:
    prev_c = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_c).abs(),
        (low - prev_c).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean().bfill()

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = _flatten_columns(df)
    idx = df.index

    c_open  = next((c for c in ["open","o"] if c in df.columns), None)
    c_high  = next((c for c in ["high","h"] if c in df.columns), None)
    c_low   = next((c for c in ["low","l"] if c in df.columns), None)
    c_close = next((c for c in ["close","c","price","last","adj_close"] if c in df.columns), None)
    c_vol   = next((c for c in ["volume","vol","v"] if c in df.columns), None)

    if not all([c_open,c_high,c_low,c_close]):
        raise KeyError(f"Missing OHLC columns in {list(df.columns)}")

    open_s  = _to_1d_series(pd.to_numeric(df[c_open], errors="coerce"), index=idx)
    high_s  = _to_1d_series(pd.to_numeric(df[c_high], errors="coerce"), index=idx)
    low_s   = _to_1d_series(pd.to_numeric(df[c_low], errors="coerce"), index=idx)
    close_s = _to_1d_series(pd.to_numeric(df[c_close], errors="coerce"), index=idx)
    vol_s   = _to_1d_series(pd.to_numeric(df[c_vol], errors="coerce"), index=idx) if c_vol else pd.Series(np.nan, index=idx)

    sma10 = close_s.rolling(10, min_periods=1).mean()
    sma20 = close_s.rolling(20, min_periods=1).mean()
    ema12 = close_s.ewm(span=12, adjust=False).mean()
    ema26 = close_s.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    macd_hist = macd - macd_signal
    rsi14 = _rsi(close_s, 14)
    atr14 = _atr(high_s, low_s, close_s, 14)

    feats = pd.DataFrame({
        "rsi14": rsi14,
        "sma10": sma10,
        "sma20": sma20,
        "ema12": ema12,
        "ema26": ema26,
        "macd": macd,
        "macd_signal": macd_signal,
        "macd_hist": macd_hist,
        "atr14": atr14
    }, index=idx)

    return feats.bfill().ffill()[FEATURES]
