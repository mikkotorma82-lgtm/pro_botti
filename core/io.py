from __future__ import annotations
from pathlib import Path as _Path
import pandas as pd

def _read_any(p: _Path) -> pd.DataFrame:
    s = p.suffix.lower()
    if s == ".parquet" or p.name.endswith(".parquet"):
        for eng in ("pyarrow", "fastparquet", None):
            try:
                return pd.read_parquet(p, engine=eng) if eng else pd.read_parquet(p)
            except Exception:
                pass
        return pd.read_parquet(p)
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
        return pd.DataFrame(columns=["time","open","high","low","close","volume"])
    return df

def _coerce_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    for c in ("open","high","low","close","volume"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        else:
            df[c] = pd.Series(dtype="float64")
    return df

def load_history(base, symbol, tf) -> pd.DataFrame:
    base_path = _Path(base)
    (base_path / "history").mkdir(parents=True, exist_ok=True)

    stem = f"{symbol}_{tf}"
    candidates = [
        base_path / "history" / f"{stem}.parquet",
        base_path / "history" / f"{stem}.feather",
        base_path / "history" / f"{stem}.csv",
        base_path / "history" / f"{stem}.csv.gz",
        base_path / f"{stem}.parquet",
        base_path / f"{stem}.feather",
        base_path / f"{stem}.csv",
        base_path / f"{stem}.csv.gz",
    ]

    p = next((c for c in candidates if c.exists()), None)
    if p is None:
        return pd.DataFrame(columns=["time","open","high","low","close","volume"])

    try:
        df = _read_any(p)
    except Exception:
        return pd.DataFrame(columns=["time","open","high","low","close","volume"])

    df = _coerce_time(df)
    df = _coerce_ohlc(df)
    if "time" in df.columns:
        df = (df.dropna(subset=["time"])
                .sort_values("time")
                .drop_duplicates(subset=["time"])
                .reset_index(drop=True))
    return df
