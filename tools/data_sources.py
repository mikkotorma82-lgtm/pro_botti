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
    # CCXT: käytä vain ..USDT -pareille
    s = str(sym).upper().strip()
    return s.endswith("USDT") or ("/USDT" in s)

def _to_ccxt_symbol(sym: str) -> str:
    s = str(sym).upper().strip()
    if "/" in s: 
        return s
    if s.endswith("USDT"):
        return f"{s[:-4]}/USDT"
    return s

def _tf_to_ccxt(tf: str) -> str:
    return str(tf).lower().strip()

# YF-käännökset: palautetaan lista kandidaatteja (yritetään järjestyksessä)
def _yf_candidates(sym: str) -> List[str]:
    s = str(sym).upper().strip()
    m: dict[str, List[str]] = {
        # Indeksit
        "US500":  ["^GSPC"],                   # S&P 500
        "SPX500": ["^GSPC"],
        "US100":  ["^NDX", "^IXIC"],           # Nasdaq 100, Composite fallback
        "NAS100": ["^NDX", "^IXIC"],
        "DJ30":   ["^DJI"],                    # Dow Jones
        "GER40":  ["^GDAXI"],                  # DAX
        "UK100":  ["^FTSE"],                   # FTSE 100
        "FRA40":  ["^FCHI"],                   # CAC 40
        "EU50":   ["^STOXX50E", "^STOXX50"],   # Euro Stoxx 50
        "JPN225": ["^N225"],                   # Nikkei 225
        # Forex (=X-suffix)
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
        "XAUUSD": ["XAUUSD=X", "GC=F"],        # spot tai futuuri
        "XAGUSD": ["XAGUSD=X", "SI=F"],
        # Energia
        "XTIUSD": ["CL=F"],                    # WTI
        "XBRUSD": ["BZ=F"],                    # Brent
        "XNGUSD": ["NG=F"],                    # Natural Gas
        # Crypto USD yfinance
        "BTCUSD": ["BTC-USD"],
        "ETHUSD": ["ETH-USD"],
        "XRPUSD": ["XRP-USD"],
        "SOLUSD": ["SOL-USD"],
        "ADAUSD": ["ADA-USD"],
    }
    if s in m:
        return m[s]
    # Valmiiksi yfinance-tyylinen (esim. BTC-USD)
    if s.endswith("-USD") or s.endswith("=X"):
        return [s]
    # Muut (osakkeet jne. AAPL, MSFT...)
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
            continue
    return None

def _pick_col(df: pd.DataFrame, names: List[str]) -> Optional[str]:
    # poimi ensimmäinen olemassa oleva sarake (case-insensitive)
    cols = {str(c).lower(): c for c in df.columns}
    for n in names:
        k = n.lower()
        if k in cols:
            return cols[k]
    return None

def _normalize_yf(df: pd.DataFrame) -> pd.DataFrame:
    """
    Muunna mitä tahansa yfinance.download -palautetta muotoon:
    columns = [time, open, high, low, close, volume], UTC
    """
    if df is None or df.empty:
        return pd.DataFrame()

    z = df.copy()

    # MultiIndex (ticker first level) -> pudota multi ja ota yksittäinen sarasetti
    if isinstance(z.columns, pd.MultiIndex):
        # jos MultiIndex, yritetään ottaa ensimmäinen taso jokaisesta hinnasta
        z.columns = ["_".join(map(str, [lvl for lvl in tup if lvl is not None])) for tup in z.columns]
        # Etsi yleisimmät nimet
        cand = {
            "Open":  _pick_col(z, ["Open","open"]),
            "High":  _pick_col(z, ["High","high"]),
            "Low":   _pick_col(z, ["Low","low"]),
            "Close": _pick_col(z, ["Adj Close","Close","close","adj_close","adjclose"]),
            "Volume":_pick_col(z, ["Volume","volume"]),
        }
        zz = pd.DataFrame()
        for std, col in cand.items():
            if col is not None and col in z.columns:
                zz[std] = pd.to_numeric(z[col], errors="coerce")
            else:
                zz[std] = np.nan
        z = zz
    else:
        # Yhden tason sarakkeet
        # Salli adj close -> close
        cand = {
            "Open":   _pick_col(z, ["Open","open"]),
            "High":   _pick_col(z, ["High","high"]),
            "Low":    _pick_col(z, ["Low","low"]),
            "Close":  _pick_col(z, ["Adj Close","Close","close","adj_close","adjclose"]),
            "Volume": _pick_col(z, ["Volume","volume"]),
        }
        zz = pd.DataFrame()
        for std, col in cand.items():
            if col is not None and col in z.columns:
                zz[std] = pd.to_numeric(z[col], errors="coerce")
            else:
                zz[std] = np.nan
        z = zz

    # Puhdista rivit joissa kaikki puuttuu
    z = z.dropna(how="all")
    # Täydennä puuttuvat volyymit nollilla
    if "Volume" in z:
        z["Volume"] = z["Volume"].fillna(0.0)

    # indeksi -> time
    z = z.reset_index()
    # yritä löytää indeksisarake (DatetimeIndex -> 'index' tai 'Date', 'Datetime')
    if "Datetime" in z.columns:
        time_col = "Datetime"
    elif "Date" in z.columns:
        time_col = "Date"
    elif "index" in z.columns:
        time_col = "index"
    else:
        # fallback: ensimmäinen sarake
        time_col = z.columns[0]

    z.rename(columns={time_col: "time"}, inplace=True)

    z["time"] = pd.to_datetime(z["time"], utc=True, errors="coerce")
    z = z.dropna(subset=["time"])

    # Uudelleennimeä pieniksi
    z = z.rename(columns={"Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume"})
    z = z[["time","open","high","low","close","volume"]].dropna()
    return z

def fetch_ohlcv(sym: str, tf: str, lookback_days: int) -> pd.DataFrame:
    tf = str(tf).lower().strip()
    s  = str(sym).strip()

    # Crypto (ccxt) vain ..USDT -pareille
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

    # 15m: max ~60d
    if tf == "15m":
        raw = _yf_download_first_ok(candidates, interval="15m", period=f"{min(int(lookback_days),60)}d")
        return _normalize_yf(raw) if raw is not None else pd.DataFrame()

    # 1h: jopa ~730d
    if tf == "1h":
        raw = _yf_download_first_ok(candidates, interval="1h", period=f"{min(int(lookback_days),730)}d")
        return _normalize_yf(raw) if raw is not None else pd.DataFrame()

    # 4h: resample 1h → 4h normalisoidusta datasta
    if tf == "4h":
        raw = _yf_download_first_ok(candidates, interval="1h", period=f"{min(int(lookback_days),730)}d")
        if raw is None or raw.empty:
            return pd.DataFrame()
        norm = _normalize_yf(raw)
        if norm is None or norm.empty:
            return pd.DataFrame()
        # resample 4h
        zz = norm.set_index("time")[["open","high","low","close","volume"]]
        o = zz.resample("4h", label="right", closed="right").agg({
            "open":"first","high":"max","low":"min","close":"last","volume":"sum"
        }).dropna()
        o = o.reset_index()
        return o

    # fallback: päivätaso
    raw = _yf_download_first_ok(candidates, interval="1d", period=f"{int(lookback_days)}d")
    return _normalize_yf(raw) if raw is not None else pd.DataFrame()
