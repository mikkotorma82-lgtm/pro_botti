
from __future__ import annotations
from pathlib import Path
import pandas as pd

def _read_any(p: Path) -> pd.DataFrame:
    s = p.suffix.lower()
    if s == ".parquet" or p.name.endswith(".parquet"):
        for eng in ("pyarrow", "fastparquet", None):
            try:
                return pd.read_parquet(p, engine=eng) if eng else pd.read_parquet(p)
            except Exception:
                pass
        return pd.read_parquet(p)  # anna kaatua
    if s == ".feather" or p.name.endswith(".feather"):
        return pd.read_feather(p)
    if s == ".csv" or p.name.endswith(".csv") or p.name.endswith(".csv.gz"):
        return pd.read_csv(p)
    raise ValueError(f"Unknown file type: {p}")

def _coerce_time(df: pd.DataFrame) -> pd.DataFrame:
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    elif df.index.name == "time" or ("time" in (df.index.names or [])):
        df = df.reset_index()
        df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    else:
        raise KeyError("No 'time' column or index in history DataFrame")
    return df

def _coerce_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    for c in ("open","high","low","close","volume"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

def load_history(base: Path, symbol: str, tf: str) -> pd.DataFrame:
    base = Path(base)
    candidates = [
        base / f"{symbol}_{tf}.parquet",
        base / f"{symbol}_{tf}.feather",
        base / f"{symbol}_{tf}.csv",
        base / f"{symbol}_{tf}.csv.gz",
    ]
    p = next((c for c in candidates if c.exists()), None)
    if p is None:
        raise FileNotFoundError(f"History file not found for {symbol} {tf} under {base}")
    df = _read_any(p)
    df = _coerce_time(df)
    df = _coerce_ohlc(df)
    df = df.dropna(subset=["time"])
    df = df.sort_values("time").drop_duplicates(subset=["time"])
    df = df.reset_index(drop=True)
    return df
