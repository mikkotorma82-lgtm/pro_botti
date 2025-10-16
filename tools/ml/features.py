from __future__ import annotations
import numpy as np
import pandas as pd

def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def _sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()

def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    up = (delta.clip(lower=0)).ewm(alpha=1/n, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    rs = up / (down.replace(0, np.nan))
    rsi = 100 - (100 / (1 + rs))
    return rsi.bfill()

def _macd(close: pd.Series, fast=12, slow=26, sig=9):
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    macd = ema_fast - ema_slow
    signal = _ema(macd, sig)
    hist = macd - signal
    return macd, signal, hist

def _zscore(s: pd.Series, n: int = 50) -> pd.Series:
    m = s.rolling(n, min_periods=n).mean()
    sd = s.rolling(n, min_periods=n).std()
    return (s - m) / (sd.replace(0, np.nan))

def _stoch_kd(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14, d: int = 3):
    ll = low.rolling(n, min_periods=n).min()
    hh = high.rolling(n, min_periods=n).max()
    k = 100 * (close - ll) / (hh - ll).replace(0, np.nan)
    dline = k.rolling(d, min_periods=d).mean()
    return k.bfill(), dline.bfill()

def _atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=n).mean().bfill()

def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    f = pd.DataFrame(index=df.index)
    close = df["close"]
    f["sma20"] = _sma(close, 20)
    f["sma50"] = _sma(close, 50)
    f["ema21"] = _ema(close, 21)
    f["ema50"] = _ema(close, 50)
    f["sma_diff"] = f["sma20"] - f["sma50"]
    f["ema_diff"] = f["ema21"] - f["ema50"]
    f["rsi14"] = _rsi(close, 14)
    macd, macds, mach = _macd(close, 12, 26, 9)
    f["macd"] = macd
    f["macd_sig"] = macds
    f["macd_hist"] = mach
    ret1 = close.pct_change()
    f["ret1"] = ret1
    f["vola50"] = ret1.rolling(50, min_periods=10).std()
    f["ret1_z"] = _zscore(ret1, 50)
    if {"high","low","close"}.issubset(df.columns):
        high, low = df["high"], df["low"]
        rng = (high - low).replace(0, np.nan)
        f["rng_pct"] = (rng / df["close"]).rolling(14, min_periods=5).mean()
        # ADX/ATR/Stoch lasketaan muissa funktioissa; jos käytät laajaa featurerunkoa, pidä ne vastaavassa tiedostossa.
    return f.replace([np.inf, -np.inf], np.nan)
