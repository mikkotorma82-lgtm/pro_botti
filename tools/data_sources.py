#!/usr/bin/env python3
from __future__ import annotations
import os, time
from typing import List, Optional
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

def _is_crypto_ccxt(sym: str) -> bool:
    s = str(sym).upper().strip()
    return s.endswith("USDT") or ("/USDT" in s)

def _to_ccxt_symbol(sym: str) -> str:
    s = str(sym).upper().strip()
    if "/" in s: return s
    if s.endswith("USDT"): return f"{s[:-4]}/USDT"
    return s

def _tf_to_ccxt(tf: str) -> str:
    return str(tf).lower().strip()

def _yf_candidates(sym: str) -> List[str]:
    s = str(sym).upper().strip()
    m: dict[str, List[str]] = {
        # Indeksit
        "US500":  ["^GSPC"],
        "SPX500": ["^GSPC"],
        "US100":  ["^NDX", "^IXIC"],
        "NAS100": ["^NDX", "^IXIC"],
        "DJ30":   ["^DJI"],
        "GER40":  ["^GDAXI"],
        "UK100":  ["^FTSE"],
        "FRA40":  ["^FCHI"],
        "EU50":   ["^STOXX50E", "^STOXX50"],
        "JPN225": ["^N225"],
        # Forex (=X)
        "EURUSD": ["EURUSD=X"],
        "GBPUSD": ["GBPUSD=X"],
        "USDJPY": ["USDJPY=X"],
        "USDCHF": ["USDCHF=X"],
        "AUDUSD": ["AUDUSD=X"],
        "USDCAD": ["USDCAD=X"],
        "NZDUSD": ["NZDUSD=X"],
        "EURJPY": ["EURJPY=X"],
        "GBPJPY": ["GBPJPY=X"],
        # Kulta/hopea, energia (futuurit fallback)
        "XAUUSD": ["XAUUSD=X", "GC=F"],
        "XAGUSD": ["XAGUSD=X", "SI=F"],
        "XTIUSD": ["CL=F"],
        "XBRUSD": ["BZ=F"],
        "XNGUSD": ["NG=F"],
        # Crypto USD yfinance
        "BTCUSD": ["BTC-USD"],
        "ETHUSD": ["ETH-USD"],
        "XRPUSD": ["XRP-USD"],
        "SOLUSD": ["SOL-USD"],
        "ADAUSD": ["ADA-USD"],
    }
    if s in m: return m[s]
    if s.endswith("-USD") or s.endswith("=X"): return [s]
    return [s]

def _sleep_delay():
    try:
        return float(os.getenv("YF_DELAY", "1.0"))
    except Exception:
        return 1.0

def _yf_download_first_ok(tickers: List[str], interval: str, period: str, retries: int = 2) -> Optional[pd.DataFrame]:
    if yf is None:
        return None
    delay = _sleep_delay()
    for t in tickers:
        for k in range(retries):
            try:
                time.sleep(delay)  # throttle to avoid rate-limits
                df = yf.download(t, interval=interval, period=period, auto_adjust=False, progress=False, threads=False)
                if df is not None and not df.empty:
                    df.attrs["ticker_used"] = t
                    return df
            except Exception:
                time.sleep(delay)
                continue
    return None

def _pick_col(df: pd.DataFrame, names: List[str]) -> Optional[str]:
    cols = {str(c).lower(): c for c in df.columns}
    for n in names:
        k = n.lower()
        if k in cols:
            return cols[k]
    return None

def _normalize_yf(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    z = df.copy()

    # MultiIndex -> flatten
    if isinstance(z.columns, pd.MultiIndex):
        z.columns = ["_".join([str(x) for x in tup if x is not None]) for tup in z.columns]

    # Poimi sarakkeet joustavasti (myös Adj Close)
    cand = {
        "Open":   _pick_col(z, ["Open","open"]),
        "High":   _pick_col(z, ["High","high"]),
        "Low":    _pick_col(z, ["Low","low"]),
        "Close":  _pick_col(z, ["Adj Close","Close","close","adj_close","adjclose"]),
        "Volume": _pick_col(z, ["Volume","volume"]),
    }
    out = pd.DataFrame()
    for std, col in cand.items():
        if col is not None and col in z.columns:
            out[std] = pd.to_numeric(z[col], errors="coerce")
        else:
            out[std] = np.nan

    out = out.dropna(how="all")
    if "Volume" in out:
        out["Volume"] = out["Volume"].fillna(0.0)

    out = out.reset_index()
    # Etsi aika-sarake
    if "Datetime" in out.columns:
        time_col = "Datetime"
    elif "Date" in out.columns:
        time_col = "Date"
    elif "index" in out.columns:
        time_col = "index"
    else:
        time_col = out.columns[0]
    out.rename(columns={time_col: "time"}, inplace=True)

    out["time"] = pd.to_datetime(out["time"], utc=True, errors="coerce")
    out = out.dropna(subset=["time"])
    out = out.rename(columns={"Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume"})
    out = out[["time","open","high","low","close","volume"]].dropna()
    return out

def fetch_ohlcv(sym: str, tf: str, lookback_days: int) -> pd.DataFrame:
    tf = str(tf).lower().strip()
    s  = str(sym).strip()

    # Crypto (ccxt) vain ..USDT-pareille → saat intraday varmasti
    if _is_crypto_ccxt(s):
        if ccxt is None:
            raise RuntimeError("ccxt puuttuu (pip install ccxt)")
        ex = ccxt.binance({"enableRateLimit": True})
        since = int((time.time() - int(lookback_days)*86400) * 1000)
        rows: list[list[float]] = []
        last = since
        while True:
            batch = ex.fetch_ohlcv(_to_ccxt_symbol(s), timeframe=_tf_to_ccxt(tf), since=last, limit=1000)
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < 1000 or len(rows) >= 4000:
                break
            last = int(batch[-1][0]) + 1
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=["time","open","high","low","close","volume"])
        df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
        return df

    # Muut → yfinance (osakkeet/indeksit/forex/commodities)
    candidates = _yf_candidates(s)

    if tf == "15m":
        raw = _yf_download_first_ok(candidates, interval="15m", period=f"{min(int(lookback_days),60)}d")
        return _normalize_yf(raw) if raw is not None else pd.DataFrame()

    if tf == "1h":
        raw = _yf_download_first_ok(candidates, interval="1h", period=f"{min(int(lookback_days),730)}d")
        return _normalize_yf(raw) if raw is not None else pd.DataFrame()

    if tf == "4h":
        # 4h normalisoidusta 1h:sta
        raw = _yf_download_first_ok(candidates, interval="1h", period=f"{min(int(lookback_days),730)}d")
        if raw is None or raw.empty:
            return pd.DataFrame()
        norm = _normalize_yf(raw)
        if norm is None or norm.empty:
            return pd.DataFrame()
        zz = norm.set_index("time")[["open","high","low","close","volume"]]
        o = zz.resample("4h", label="right", closed="right").agg({
            "open":"first","high":"max","low":"min","close":"last","volume":"sum"
        }).dropna()
        return o.reset_index()

    # fallback: päivätaso
    raw = _yf_download_first_ok(candidates, interval="1d", period=f"{int(lookback_days)}d")
    return _normalize_yf(raw) if raw is not None else pd.DataFrame()
