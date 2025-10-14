#!/usr/bin/env python3
from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Optional, Dict, List
import numpy as np
import pandas as pd

try:
    import ccxt  # type: ignore
except Exception:
    ccxt = None

try:
    import yfinance as yf  # type: ignore
except Exception:
    yf = None

@dataclass
class OHLCV:
    time: pd.Series
    open: pd.Series
    high: pd.Series
    low: pd.Series
    close: pd.Series
    volume: pd.Series

def _yf_symbol_map(sym: str) -> str:
    m = {
        "US500": "^GSPC", "SPX500": "^GSPC",
        "US100": "^NDX",  "NAS100": "^NDX",
        "DJ30": "^DJI",   "GER40": "^GDAXI", "UK100": "^FTSE",
        "BTCUSD": "BTC-USD", "ETHUSD": "ETH-USD", "XRPUSD": "XRP-USD",
        "SOLUSD": "SOL-USD", "ADAUSD": "ADA-USD",
    }
    return m.get(sym, sym)

def _is_crypto(sym: str) -> bool:
    return sym.endswith("USDT") or ("/USDT" in sym)

def _to_ccxt_symbol(sym: str) -> str:
    if "/" in sym: return sym
    if sym.endswith("USDT"): return f"{sym[:-4]}/USDT"
    return sym

def _tf_to_ccxt(tf: str) -> str:
    return tf.lower()

def _resample_ohlcv_4h(df: pd.DataFrame) -> pd.DataFrame:
    cols = {c.lower(): c for c in df.columns}
    o = df.resample("4H", label="right", closed="right").agg({
        cols.get("open","Open"): "first",
        cols.get("high","High"): "max",
        cols.get("low","Low"): "min",
        cols.get("close","Close"): "last",
        cols.get("volume","Volume"): "sum",
    }).dropna()
    o = o.rename(columns={"Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume"})
    return o

def _normalize_yf(df: pd.DataFrame) -> pd.DataFrame:
    z = df.copy()
    if isinstance(z.columns, pd.MultiIndex):
        z.columns = z.columns.get_level_values(0)
    ren = {"Open": "open", "High": "high", "Low": "low", "Close": "close", "Adj Close": "close", "Volume": "volume"}
    z = z.rename(columns=ren)
    need = ["open","high","low","close","volume"]
    for c in need:
        if c not in z.columns: z[c] = np.nan
    z = z[need].dropna()
    z = z.reset_index().rename(columns={z.index.name or "index":"time"})
    if not pd.api.types.is_datetime64_any_dtype(z["time"]):
        z["time"] = pd.to_datetime(z["time"], utc=True)
    else:
        z["time"] = z["time"].dt.tz_convert("UTC") if z["time"].dt.tz is not None else z["time"].dt.tz_localize("UTC")
    return z

def fetch_ohlcv(sym: str, tf: str, lookback_days: int) -> pd.DataFrame:
    tf = tf.lower().strip()
    if _is_crypto(sym):
        if ccxt is None:
            raise RuntimeError("ccxt puuttuu (pip install ccxt)")
        ex = ccxt.binance({"enableRateLimit": True})
        since = int((time.time() - lookback_days*86400) * 1000)
        rows = []; last = since
        while True:
            batch = ex.fetch_ohlcv(_to_ccxt_symbol(sym), timeframe=_tf_to_ccxt(tf), since=last, limit=1000)
            if not batch: break
            rows.extend(batch)
            if len(batch) < 1000 or len(rows) >= 4000: break
            last = int(batch[-1][0]) + 1
        if not rows: return pd.DataFrame()
        df = pd.DataFrame(rows, columns=["time","open","high","low","close","volume"])
        df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
        return df

    if yf is None:
        raise RuntimeError("yfinance puuttuu (pip install yfinance)")
    ticker = _yf_symbol_map(sym)

    if tf == "15m":
        interval = "15m"; period_days = min(lookback_days, 60)
        df = yf.download(ticker, interval=interval, period=f"{period_days}d", auto_adjust=False, progress=False)
        if df is None or df.empty: return pd.DataFrame()
        return _normalize_yf(df)

    if tf == "1h":
        interval = "1h"; period_days = min(lookback_days, 730)
        df = yf.download(ticker, interval=interval, period=f"{period_days}d", auto_adjust=False, progress=False)
        if df is None or df.empty: return pd.DataFrame()
        return _normalize_yf(df)

    if tf == "4h":
        interval = "1h"; period_days = min(lookback_days, 730)
        raw = yf.download(ticker, interval=interval, period=f"{period_days}d", auto_adjust=False, progress=False)
        if raw is None or raw.empty: return pd.DataFrame()
        if not isinstance(raw.index, pd.DatetimeIndex):
            raw.index = pd.to_datetime(raw.index, utc=True)
        o = _resample_ohlcv_4h(raw)
        if o is None or o.empty: return pd.DataFrame()
        o = o.reset_index().rename(columns={"index":"time"})
        if not pd.api.types.is_datetime64_any_dtype(o["time"]):
            o["time"] = pd.to_datetime(o["time"], utc=True)
        else:
            o["time"] = o["time"].dt.tz_convert("UTC") if o["time"].dt.tz is not None else o["time"].dt.tz_localize("UTC")
        return o

    raw = yf.download(ticker, interval="1d", period=f"{lookback_days}d", auto_adjust=False, progress=False)
    if raw is None or raw.empty: return pd.DataFrame()
    return _normalize_yf(raw)
