#!/usr/bin/env python3
from __future__ import annotations
import os
from pathlib import Path
import pandas as pd

CAP_DIR = Path(os.getenv("CAPITAL_CACHE_DIR", "data/capital")).resolve()

def list_cached():
    if not CAP_DIR.exists():
        return []
    return sorted([p for p in CAP_DIR.glob("*.parquet")] + [p for p in CAP_DIR.glob("*.csv")])

def load_cached(symbol: str, tf: str) -> pd.DataFrame:
    base = f"{''.join(ch if ch.isalnum() or ch in '-_.' else '_' for ch in symbol)}__{tf}"
    pq = CAP_DIR / f"{base}.parquet"
    cs = CAP_DIR / f"{base}.csv"
    if pq.exists():
        df = pd.read_parquet(pq)
    elif cs.exists():
        df = pd.read_csv(cs)
        if "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    else:
        return pd.DataFrame()
    # standard columns
    exp = ["time","open","high","low","close","volume"]
    for c in exp:
        if c not in df.columns:
            df[c] = None
    df = df[exp].dropna(subset=["time"]).sort_values("time").reset_index(drop=True)
    return df
