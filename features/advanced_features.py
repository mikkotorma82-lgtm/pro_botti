#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CapitalBot – Advanced Feature Engineering (Capital.com only)
- Lukee /data/history/*.csv, kirjoittaa /data/features/*.csv
- Ei ulkoisia makro-lähteitä
"""
import pandas as pd, numpy as np
from pathlib import Path
from ta.momentum import RSIIndicator
from ta.trend import MACD, EMAIndicator
from ta.volatility import BollingerBands, AverageTrueRange
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA

BASE = Path(__file__).resolve().parents[1]
SRC  = BASE / "data" / "history"
DEST = BASE / "data" / "features"
DEST.mkdir(parents=True, exist_ok=True)

SYMBOLS = [
    "BTCUSD","ETHUSD","XRPUSD","ADAUSD","SOLUSD",
    "US500","US100","DE40","JP225",
    "AAPL","NVDA","TSLA","AMZN","MSFT","META","GOOGL",
    "EURUSD","GBPUSD"
]
TIMEFRAMES = ["1h","4h"]

def add_features(df: pd.DataFrame)->pd.DataFrame:
    df = df.copy()
    df["time"] = pd.to_datetime(df["time"])
    df.sort_values("time", inplace=True)

    df["return"]    = df["close"].pct_change()
    df["ema10"]     = EMAIndicator(df["close"],10).ema_indicator()
    df["ema30"]     = EMAIndicator(df["close"],30).ema_indicator()
    macd            = MACD(df["close"])
    df["macd"]      = macd.macd()
    df["rsi"]       = RSIIndicator(df["close"]).rsi()
    bb              = BollingerBands(df["close"])
    df["bbp"]       = bb.bollinger_pband()
    df["atr"]       = AverageTrueRange(df["high"],df["low"],df["close"]).average_true_range()
    df["mom10"]     = df["close"].diff(10)
    df["atr_ratio"] = df["atr"]/df["close"]

    return df.dropna()

def add_pca(df: pd.DataFrame, n=3)->pd.DataFrame:
    feats = ["ema10","ema30","macd","rsi","bbp","atr","mom10"]
    sub = df[feats].dropna()
    if len(sub) < 50:
        return df
    X = StandardScaler().fit_transform(sub)
    comp = PCA(n_components=n).fit_transform(X)
    for i in range(n):
        df[f"pca{i+1}"] = np.nan
        df.loc[sub.index, f"pca{i+1}"] = comp[:,i]
    return df

def process(symbol, tf):
    path = SRC / f"{symbol}_{tf}.csv"
    if not path.exists():
        print(f"[skip] {path} missing")
        return
    df = pd.read_csv(path)
    needed = {"time","open","high","low","close","volume"}
    if not needed.issubset(df.columns):
        print(f"[skip] {path} bad columns")
        return
    df = add_features(df)
    df = add_pca(df, n=3)
    out = DEST / f"{symbol}_{tf}.csv"
    df.to_csv(out, index=False)
    print(f"[ok] {symbol}_{tf} -> {out} ({len(df)} rows)")

def main():
    for s in SYMBOLS:
        for tf in TIMEFRAMES:
            process(s, tf)
    print("[done] advanced features (Capital.com only)")
if __name__ == "__main__":
    main()
