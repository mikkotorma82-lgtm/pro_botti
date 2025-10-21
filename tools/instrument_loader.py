from __future__ import annotations
import pandas as pd
import numpy as np
import yfinance as yf

# Yksi vakio-API: get_ohlcv(symbol, tf) -> DataFrame(index=UTC DatetimeIndex, cols: open, high, low, close, volume)
def get_ohlcv(symbol: str, tf: str) -> pd.DataFrame:
    tf = tf.strip().lower()

    # yfinance intervallit & periodit (intraday-rajat yfin:ssa)
    if tf in ("15m", "15min", "15"):
        interval = "15m"
        period = "60d"   # max yfin 1m/2m/5m/15m/30m: 60d
        df = yf.download(tickers=symbol, interval=interval, period=period, progress=False, auto_adjust=False, prepost=False, threads=False)
    elif tf in ("1h", "60m", "1hour"):
        interval = "60m"
        period = "730d"  # max yfin 60m: 730d
        df = yf.download(tickers=symbol, interval=interval, period=period, progress=False, auto_adjust=False, prepost=False, threads=False)
    elif tf in ("4h", "240m", "4hour"):
        # Yfin ei tarjoa 4h suoraan; hae 60m ja resamplaa 4H:ksi
        interval = "60m"
        period = "730d"
        df60 = yf.download(tickers=symbol, interval=interval, period=period, progress=False, auto_adjust=False, prepost=False, threads=False)
        if df60.empty:
            return pd.DataFrame(columns=["open","high","low","close","volume"])
        if df60.index.tz is None:
            df60.index = df60.index.tz_localize("UTC")
        else:
            df60.index = df60.index.tz_convert("UTC")
        # Standardoi kolumnit ennen resamplausta
        df60 = df60.rename(columns={"Open":"open","High":"high","Low":"low","Close":"close","Adj Close":"adj_close","Volume":"volume"})
        # OHLCV resample 4H
        ohlc = df60[["open","high","low","close"]].resample("4H", label="right", closed="right").agg({
            "open":"first", "high":"max", "low":"min", "close":"last"
        })
        vol = df60[["volume"]].resample("4H", label="right", closed="right").sum()
        df = pd.concat([ohlc, vol], axis=1)
        df = df.dropna(how="any")
        return df

    else:
        raise ValueError(f"Unsupported timeframe: {tf} (supported: 15m, 1h, 4h)")

    # Normalisoi (yfinance -> meidän schema)
    if df.empty:
        return pd.DataFrame(columns=["open","high","low","close","volume"])
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")

    df = df.rename(columns={"Open":"open","High":"high","Low":"low","Close":"close","Adj Close":"adj_close","Volume":"volume"})
    cols = [c for c in ["open","high","low","close","volume"] if c in df.columns]
    out = df[cols].copy()
    # siivoa duplikaatit & järjestys
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out
