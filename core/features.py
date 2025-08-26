from __future__ import annotations
import pandas as pd
import numpy as np

def ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()

def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
    down = (-d.clip(upper=0)).ewm(alpha=1/period, adjust=False).mean()
    rs = up / (down + 1e-12)
    return 100 - (100 / (1 + rs))

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()

def make_features(df: pd.DataFrame):
    z = df.copy()
    z = z.sort_values("time").reset_index(drop=True)
    z["ret1"] = z["close"].pct_change()
    z["ret5"] = z["close"].pct_change(5)
    z["vol5"] = z["ret1"].rolling(48, min_periods=12).std()
    z["ema12"] = ema(z["close"], 12)
    z["ema26"] = ema(z["close"], 26)
    z["macd"] = z["ema12"] - z["ema26"]
    z["rsi14"] = rsi(z["close"], 14)
    z["atr14"] = atr(z, 14) / (z["close"] + 1e-12)
    z["ema_gap"] = (z["close"] - z["ema12"]) / (z["ema12"] + 1e-12)
    z = z.dropna().reset_index(drop=True)
    feats = ["ret1","ret5","vol5","ema12","ema26","macd","rsi14","atr14","ema_gap"]
    return z, feats
