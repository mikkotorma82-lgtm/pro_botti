import os, sys, json, time, datetime as dt
import pandas as pd
import yfinance as yf

YF = {
  "AAPL":"AAPL","NVDA":"NVDA","TSLA":"TSLA",
  "US100":"^NDX","US500":"^GSPC",
  "EURUSD":"EURUSD=X","GBPUSD":"GBPUSD=X",
  "BTCUSD":"BTC-USD","ETHUSD":"ETH-USD",   # Crypto: käytä 4h täältä, muut ccxt
}
POLICY = {
  "15m": ("15m", 59, 0.16),   # ~60 pv
  "1h" : ("60m", 700, 2.0),   # ~730 pv
  "4h" : ("60m", 700, 10.0),  # haetaan 60m ja resamplataan 4h
}

def ensure_dir(p): os.makedirs(os.path.dirname(p), exist_ok=True)

def dl_chunks(tkr, interval, start, end, chunk_days):
    out=[]; s=start
    while s<end:
        e=min(s+dt.timedelta(days=chunk_days), end)
        df = yf.download(tkr, interval=interval, start=s, end=e, auto_adjust=False, progress=False)
        if isinstance(df,pd.DataFrame) and not df.empty:
            if getattr(df.index,"tz",None) is not None: df = df.tz_convert(None)
            out.append(df)
        s=e; time.sleep(0.2)
    return pd.concat(out).sort_index() if out else pd.DataFrame()

def ohlc_resample(df, rule):
    o = df['Open'].resample(rule).first()
    h = df['High'].resample(rule).max()
    l = df['Low'].resample(rule).min()
    c = df['Close'].resample(rule).last()
    v = df['Volume'].resample(rule).sum(min_count=1)
    out = pd.concat([o,h,l,c,v], axis=1).dropna(how="any")
    out.columns = ['Open','High','Low','Close','Volume']
    return out

if __name__=="__main__":
    if len(sys.argv)!=3:
        print("usage: backfill_yf.py SYMBOL TF"); sys.exit(1)
    sym, tf = sys.argv[1], sys.argv[2]
    assert tf in POLICY, f"tf must be one of {list(POLICY)}"
    assert sym in YF, f"{sym} ei mapannu yfinanceen"
    INTERVAL, CHUNK, YEARS = POLICY[tf]
    tkr = YF[sym]

    end = dt.datetime.utcnow().date() + dt.timedelta(days=1)
    start = end - dt.timedelta(days=int(365.25*YEARS))

    df = dl_chunks(tkr, INTERVAL, start, end, CHUNK)
    if df.empty:
        print(json.dumps({"ok":False,"why":"no_data","sym":sym,"tf":tf})); sys.exit(0)

    if tf == "4h":
        df = ohlc_resample(df, "4H")

    df = df[~df.index.duplicated(keep="last")]
    out = pd.DataFrame({
      "time": df.index.to_pydatetime(),
      "open": df["Open"].astype(float).to_numpy().ravel(),
      "high": df["High"].astype(float).to_numpy().ravel(),
      "low":  df["Low"].astype(float).to_numpy().ravel(),
      "close":df["Close"].astype(float).to_numpy().ravel(),
      "volume": df["Volume"].fillna(0.0).astype(float).to_numpy().ravel(),
    })
    ensure_dir("data/history/_")
    path = f"data/history/{sym}_{tf}.parquet"
    out.to_parquet(path, index=False)
    print(json.dumps({"ok":True,"sym":sym,"tf":tf,"rows":len(out),"file":path}))
