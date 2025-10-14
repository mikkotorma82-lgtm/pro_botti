#!/usr/bin/env python3
from __future__ import annotations
import time
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
    # CCXT: käytä vain ..USDT-pareille
    return sym.endswith("USDT") or ("/USDT" in sym)

def _to_ccxt_symbol(sym: str) -> str:
    if "/" in sym: return sym
    if sym.endswith("USDT"): return f"{sym[:-4]}/USDT"
    return sym

def _tf_to_ccxt(tf: str) -> str:
    return str(tf).lower().strip()

# YF-käännökset: palautetaan lista kandidaatteja, joita kokeillaan järjestyksessä
def _yf_candidates(sym: str) -> List[str]:
    s = sym.upper().strip()
    m: dict[str, List[str]] = {
        # Indeksit
        "US500":  ["^GSPC"],                  # S&P 500
        "SPX500": ["^GSPC"],
        "US100":  ["^NDX", "^IXIC"],          # Nasdaq 100, Composite fallback
        "NAS100": ["^NDX", "^IXIC"],
        "DJ30":   ["^DJI"],                   # Dow Jones
        "GER40":  ["^GDAXI"],                 # DAX
        "UK100":  ["^FTSE"],                  # FTSE 100
        "FRA40":  ["^FCHI"],                  # CAC 40
        "EU50":   ["^STOXX50E", "^STOXX50"],  # Euro Stoxx 50 (vaihtelee)
        "JPN225": ["^N225"],                  # Nikkei 225
        # Forex-parit (Yahoo-tyyli = suffix "=X")
        "EURUSD": ["EURUSD=X"],
        "GBPUSD": ["GBPUSD=X"],
        "USDJPY": ["USDJPY=X"],
        "USDCHF": ["USDCHF=X"],
        "AUDUSD": ["AUDUSD=X"],
        "USDCAD": ["USDCAD=X"],
        "NZDUSD": ["NZDUSD=X"],
        "EURJPY": ["EURJPY=X"],
        "GBPJPY": ["GBPJPY=X"],
        # Kulta/hopea
        "XAUUSD": ["XAUUSD=X", "GC=F"],       # spot tai futuuri
        "XAGUSD": ["XAGUSD=X", "SI=F"],
        # Energia
        "XTIUSD": ["CL=F"],                   # WTI
        "XBRUSD": ["BZ=F"],                   # Brent
        "XNGUSD": ["NG=F"],                   # Natural Gas
        # Crypto USD (yfinance)
        "BTCUSD": ["BTC-USD"],
        "ETHUSD": ["ETH-USD"],
        "XRPUSD": ["XRP-USD"],
        "SOLUSD": ["SOL-USD"],
        "ADAUSD": ["ADA-USD"],
    }
    if s in m: 
        return m[s]
    # Jos symbolissa on jo -USD, käytä sellaisenaan
    if s.endswith("-USD"):
        return [s]
    # Muuten palauta alkuperäinen (osakkeet kuten AAPL, MSFT, NVDA, TSLA, META, AMZN)
    return [s]

def _yf_download_first_ok(tickers: List[str], interval: str, period: str) -> Optional[pd.DataFrame]:
    if yf is None:
        return None
    for t in tickers:
        try:
            df = yf.download(t, interval=interval, period=period, auto_adjust=False, progress=False)
            if df is not None and not df.empty:
                df.attrs["ticker_used"] = t
                return df
        except Exception:
            # kokeillaan seuraavaa kandidaattia
            continue
    return None

def _normalize_yf(df: pd.DataFrame) -> pd.DataFrame:
    z = df.copy()
    if isinstance(z.columns, pd.MultiIndex):
        # yksittäinen tikkeri → taso pois
        z.columns = z.columns.get_level_values(0)
    # vakiotaulukko
    ren = {"Open":"open","High":"high","Low":"low","Close":"close","Adj Close":"close","Volume":"volume"}
    z = z.rename(columns=ren)
    need = ["open","high","low","close","volume"]
    for c in need:
        if c not in z.columns:
            z[c] = np.nan
    z = z[need].dropna()
    # indeksi → sarake time (UTC)
    z = z.reset_index().rename(columns={z.index.name or "index":"time"})
    if not pd.api.types.is_datetime64_any_dtype(z["time"]):
        z["time"] = pd.to_datetime(z["time"], utc=True, errors="coerce")
    else:
        z["time"] = z["time"].dt.tz_convert("UTC") if getattr(z["time"].dt, "tz", None) is not None else z["time"].dt.tz_localize("UTC")
    z = z.dropna()
    return z

def fetch_ohlcv(sym: str, tf: str, lookback_days: int) -> pd.DataFrame:
    tf = str(tf).lower().strip()

    # Crypto (ccxt) vain ..USDT -pareille
    if _is_crypto_ccxt(sym):
        if ccxt is None:
            raise RuntimeError("ccxt puuttuu (pip install ccxt)")
        ex = ccxt.binance({"enableRateLimit": True})
        since = int((time.time() - int(lookback_days)*86400) * 1000)
        rows: list[list[float]] = []
        last = since
        while True:
            batch = ex.fetch_ohlcv(_to_ccxt_symbol(sym), timeframe=_tf_to_ccxt(tf), since=last, limit=1000)
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
    candidates = _yf_candidates(sym)

    # 15m: max ~60d
    if tf == "15m":
        df = _yf_download_first_ok(candidates, interval="15m", period=f"{min(lookback_days,60)}d")
        return _normalize_yf(df) if df is not None else pd.DataFrame()

    # 1h: jopa ~730d
    if tf == "1h":
        df = _yf_download_first_ok(candidates, interval="1h", period=f"{min(lookback_days,730)}d")
        return _normalize_yf(df) if df is not None else pd.DataFrame()

    # 4h: resample 1h → 4h
    if tf == "4h":
        raw = _yf_download_first_ok(candidates, interval="1h", period=f"{min(lookback_days,730)}d")
        if raw is None or raw.empty:
            return pd.DataFrame()
        if not isinstance(raw.index, pd.DatetimeIndex):
            raw.index = pd.to_datetime(raw.index, utc=True, errors="coerce")
        o = raw.resample("4H", label="right", closed="right").agg({
            "Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum",
        }).dropna()
        o = o.rename(columns={"Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume"})
        o = o.reset_index().rename(columns={"index":"time"})
        o["time"] = pd.to_datetime(o["time"], utc=True, errors="coerce")
        return o.dropna()

    # fallback: päivätaso
    df = _yf_download_first_ok(candidates, interval="1d", period=f"{lookback_days}d")
    return _normalize_yf(df) if df is not None else pd.DataFrame()
