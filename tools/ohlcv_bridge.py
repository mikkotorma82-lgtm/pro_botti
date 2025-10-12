import time
import pandas as pd
import yfinance as yf
try:
    from yfinance.exceptions import YFRateLimitError
except Exception:
    class YFRateLimitError(Exception):
        pass

# Yksinkertainen tf->(interval, period) -kartta (säädä tarvittaessa)
_TF_MAP = {
    "1m":  ("1m",  "7d"),
    "5m":  ("5m",  "30d"),
    "15m": ("15m", "60d"),
    "30m": ("30m", "60d"),
    "1h":  ("60m","730d"),
    "4h":  ("60m","730d"),
    "1d":  ("1d", "max"),
}

def get_ohlcv(symbol: str, tf: str) -> pd.DataFrame:
    interval, period = _TF_MAP.get(tf, ("1d", "max"))
    tkr = yf.Ticker(symbol)

    # Retry Yahoo rate limit / satunnaisvirheet
    last_err = None
    for attempt in range(3):
        try:
            df = tkr.history(interval=interval, period=period, auto_adjust=False, actions=False)
            break
        except YFRateLimitError as e:
            last_err = e
            time.sleep(2 ** attempt)
        except Exception as e:
            # joskus YFRateLimitError ei ole käytettävissä -> sama backoff
            last_err = e
            time.sleep(2 ** attempt)
    else:
        # viimeinen yritys: jos vielä virhe, heitä eteenpäin
        if last_err:
            raise last_err
        df = tkr.history(interval=interval, period=period, auto_adjust=False, actions=False)

    if df is None or df.empty:
        return pd.DataFrame(columns=["open","high","low","close","volume"])

    # Siivoa sarake-aliaksia
    cols = {c.lower(): c for c in df.columns}
    # Varma sarakeryhmä
    open_c  = cols.get("open",  "Open")
    high_c  = cols.get("high",  "High")
    low_c   = cols.get("low",   "Low")
    close_c = cols.get("close", "Close")
    vol_c   = cols.get("volume","Volume")

    out = pd.DataFrame({
        "open":  df[open_c].astype(float),
        "high":  df[high_c].astype(float),
        "low":   df[low_c].astype(float),
        "close": df[close_c].astype(float),
        "volume":df[vol_c].astype(float),
    })
    # Varmista aikaleimat indexissä
    out.index = pd.to_datetime(df.index)
    out = out[["open","high","low","close","volume"]]
    return out
