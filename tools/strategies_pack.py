#!/usr/bin/env python3
from __future__ import annotations
import numpy as np
import pandas as pd

def signal_sma(df: pd.DataFrame, n: int) -> np.ndarray:
    px = df["close"].astype(float).values
    sma = pd.Series(px).rolling(n, min_periods=n).mean().values
    sig = np.zeros_like(px, dtype=float)
    sig[~np.isnan(sma)] = np.sign(px[~np.isnan(sma)] - sma[~np.isnan(sma)])
    return sig  # -1/0/1

def signal_ema(df: pd.DataFrame, n: int) -> np.ndarray:
    px = df["close"].astype(float)
    ema = px.ewm(span=n, adjust=False, min_periods=n).mean().values
    sig = np.zeros(len(px), dtype=float)
    mask = ~np.isnan(ema)
    sig[mask] = np.sign(px.values[mask] - ema[mask])
    return sig

def signal_rsi(df: pd.DataFrame, n: int, low=30.0, high=70.0) -> np.ndarray:
    px = df["close"].astype(float).values
    delta = np.diff(px, prepend=px[0])
    up = np.where(delta > 0, delta, 0.0)
    down = -np.where(delta < 0, delta, 0.0)
    roll_up = pd.Series(up).rolling(n, min_periods=n).mean().values
    roll_down = pd.Series(down).rolling(n, min_periods=n).mean().values
    rs = np.divide(roll_up, roll_down + 1e-12)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    sig = np.zeros_like(px, dtype=float)
    # Oversold -> buy, Overbought -> sell
    sig[rsi <= low] = 1.0
    sig[rsi >= high] = -1.0
    return sig

def signal_macd(df: pd.DataFrame, fast=12, slow=26, siglen=9) -> np.ndarray:
    px = df["close"].astype(float)
    ema_fast = px.ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = px.ewm(span=slow, adjust=False, min_periods=slow).mean()
    macd = ema_fast - ema_slow
    signal = macd.ewm(span=siglen, adjust=False, min_periods=siglen).mean()
    hist = macd - signal
    # Käytä histogrammin nollaristiä signaalina
    sig = np.sign(hist.values)
    return sig
