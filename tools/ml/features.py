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

def _obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    # OBV: kumulatiivinen volyymi hinnan muutoksen suunnan mukaan
    vol = volume.fillna(0)
    sign = np.sign(close.diff()).fillna(0)
    return (vol * sign).cumsum().fillna(0)

def _stoch_kd(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14, d: int = 3):
    ll = low.rolling(n, min_periods=n).min()
    hh = high.rolling(n, min_periods=n).max()
    k = 100 * (close - ll) / (hh - ll).replace(0, np.nan)
    dline = k.rolling(d, min_periods=d).mean()
    return k.fillna(method="bfill"), dline.fillna(method="bfill")

def _atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=n).mean().fillna(method="bfill")

def _adx(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14):
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr = _atr(high, low, close, n=1)  # TR per bar
    atr_n = tr.rolling(n, min_periods=n).mean().replace(0, np.nan)

    plus_di = 100 * (pd.Series(plus_dm, index=high.index).rolling(n, min_periods=n).sum() / atr_n)
    minus_di = 100 * (pd.Series(minus_dm, index=low.index).rolling(n, min_periods=n).sum() / atr_n)

    dx = ( (plus_di - minus_di).abs() / (plus_di + minus_di).abs() ) * 100
    adx = dx.rolling(n, min_periods=n).mean()
    return plus_di.fillna(method="bfill"), minus_di.fillna(method="bfill"), adx.fillna(method="bfill")

def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Palauttaa laajan featurerungon; malli/asset-luokka valitsee joukon.
    """
    f = pd.DataFrame(index=df.index)
    close = df["close"]

    # Trend/momentum-perus
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

    # Vola/Momentti/Range
    ret1 = close.pct_change()
    f["ret1"] = ret1
    f["vola50"] = ret1.rolling(50, min_periods=10).std()
    f["ret1_z"] = _zscore(ret1, 50)

    if {"high","low","close"}.issubset(df.columns):
        high, low = df["high"], df["low"]
        rng = (high - low).replace(0, np.nan)
        f["rng_pct"] = (rng / df["close"]).rolling(14, min_periods=5).mean()
        f["atr14"] = _atr(high, low, close, 14)
        plus_di, minus_di, adx = _adx(high, low, close, 14)
        f["plus_di"] = plus_di
        f["minus_di"] = minus_di
        f["adx14"] = adx
        k, d = _stoch_kd(high, low, close, 14, 3)
        f["stoch_k"] = k
        f["stoch_d"] = d

    # Volyymi (jos saatavilla)
    if "volume" in df.columns:
        f["obv"] = _obv(close, df["volume"])
    else:
        f["obv"] = 0.0

    return f.replace([np.inf, -np.inf], np.nan)
