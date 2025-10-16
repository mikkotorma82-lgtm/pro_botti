from __future__ import annotations
import os
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
    return rsi.fillna(method="bfill")

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

def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Palauttaa featuret samalle indeksille.
    FEATURE_SET=minimal -> kompakti, vähemmän korreloiva joukko.
    FEATURE_SET=full    -> kaikki alla listatut.
    """
    close = df["close"]
    f = pd.DataFrame(index=df.index)

    # Perus liukuvat
    f["sma20"] = _sma(close, 20)
    f["sma50"] = _sma(close, 50)
    f["ema21"] = _ema(close, 21)
    f["ema50"] = _ema(close, 50)
    f["sma_diff"] = f["sma20"] - f["sma50"]
    f["ema_diff"] = f["ema21"] - f["ema50"]

    # RSI / MACD
    f["rsi14"] = _rsi(close, 14)
    macd, macds, mach = _macd(close, 12, 26, 9)
    f["macd"] = macd
    f["macd_sig"] = macds
    f["macd_hist"] = mach

    # Volatiliteetti / momentti
    ret1 = close.pct_change()
    f["ret1"] = ret1
    f["vola50"] = ret1.rolling(50, min_periods=10).std()
    f["ret1_z"] = _zscore(ret1, 50)

    # Range-proxy
    if {"high","low","close"}.issubset(df.columns):
        rng = (df["high"] - df["low"]).replace(0, np.nan)
        f["rng_pct"] = (rng / df["close"]).rolling(14, min_periods=5).mean()

    set_name = (os.getenv("FEATURE_SET") or "minimal").lower().strip()
    if set_name == "full":
        # Palauta kaikki lasketut
        return f

    # Minimal setti (suositus aloitukseen)
    cols = ["sma_diff","ema_diff","rsi14","macd_hist","ret1_z","rng_pct","vola50"]
    keep = [c for c in cols if c in f.columns]
    return f[keep]
