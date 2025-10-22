
from __future__ import annotations
import os, pandas as pd, numpy as np
from typing import Optional, List, Dict
from loguru import logger

def read_ohlcv_csv(path: str, tz: str="UTC") -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    if "timestamp" not in df.columns:
        raise ValueError("CSV must have 'timestamp' column (ms or ISO8601)")
    ts = df["timestamp"]
    if ts.dtype.kind in "iuf":
        idx = pd.to_datetime(ts, unit="ms", utc=True)
    else:
        idx = pd.to_datetime(ts, utc=True)
    df.index = idx.tz_convert(tz)
    cols = ["open","high","low","close","volume"]
    for c in cols:
        if c not in df.columns:
            raise ValueError(f"CSV missing column '{c}'")
    out = df[cols].sort_index()
    return out

def resample(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    o = df["open"].resample(tf).first()
    h = df["high"].resample(tf).max()
    l = df["low"].resample(tf).min()
    c = df["close"].resample(tf).last()
    v = df["volume"].resample(tf).sum()
    out = pd.DataFrame({"open":o,"high":h,"low":l,"close":c,"volume":v}).dropna()
    return out

def merge_features(df: pd.DataFrame, feat_df: pd.DataFrame) -> pd.DataFrame:
    return df.join(feat_df, how="left").dropna()
