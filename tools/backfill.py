import os, sys, time, math, json, re
import pandas as pd
from datetime import datetime, timedelta, timezone

# Valinnainen ccxt/yf
try:
    import ccxt
except Exception:
    ccxt=None
import yfinance as yf

OUT=os.path.join(os.environ.get("ROOT","/root/pro_botti"),"data","history")
os.makedirs(OUT, exist_ok=True)

def years_to_ms(years: int) -> int:
    # 365.25 päivää/vuosi
    return int(years*365.25*24*3600*1000)

def tf_to_minutes(tf:str)->int:
    return {"15m":15, "1h":60, "4h":240}[tf]

def normalize_symbol(sym:str)->str:
    # BTCUSDT -> BTC/USDT ; ETHUSD -> ETH/USD ; EURUSD -> EUR/USD
    m = re.match(r"^([A-Z]+?)(USDT|USD|EUR|GBP)$", sym)
    return f"{m.group(1)}/{m.group(2)}" if m else sym

def is_crypto(sym:str)->bool:
    return sym.endswith(("USDT","USDC","BTC","ETH"))

def yf_ticker(sym:str)->str:
    # Forex
    if sym in ("EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","USDCHF"):
        return sym + "=X"
    # Indeksit
    if sym=="US500": return "^GSPC"
    if sym=="US100": return "^NDX"
    # osakkeet kuten AAPL, NVDA, TSLA...
    return sym

def write_parquet(path, df):
    cols = ["time","open","high","low","close","volume"]
    df = df[cols].copy()
    df.sort_values("time", inplace=True)
    df.to_parquet(path, index=False)

def fetch_crypto_ccxt(sym:str, tf:str, years:int):
    ex = ccxt.binance({'enableRateLimit': True}) if ccxt else None
    if ex is None:
        raise RuntimeError("ccxt not available")
    u = normalize_symbol(sym)
    ex.load_markets()
    if u not in ex.markets:
        raise RuntimeError(f"{sym}: symbol not supported on Binance")
    ms_per = ex.parse_timeframe(tf) * 1000
    since = ex.milliseconds() - years_to_ms(years)
    # CCXT rajoittaa ~1000–1500 kpl/fetch; haetaan paloissa
    limit = 1000
    all_rows = []
    now = ex.milliseconds()
    while since < now - ms_per:
        ohlcvs = ex.fetch_ohlcv(u, timeframe=tf, since=since, limit=limit)  # [ms, o,h,l,c,v]
        if not ohlcvs: break
        since = ohlcvs[-1][0] + ms_per
        all_rows.extend(ohlcvs)
        # kevyt throttle
        time.sleep(0.2)
    if not all_rows:
        raise RuntimeError("no data")
    df = pd.DataFrame(all_rows, columns=["time","open","high","low","close","volume"])
    write_parquet(os.path.join(OUT, f"{sym}_{tf}.parquet"), df)
    return len(df)

def fetch_yf(sym:str, tf:str, years:int):
    # yfinance intervallit: 15m (max 60d) -> joudutaan stitchaamaan;
    # 1h ja 4h saadaan helposti (max 730d per pyyntö käytännössä).
    # Tehdään varma silmukka aikavälin yli.
    itv = {"15m":"15m","1h":"60m","4h":"240m"}[tf]
    ticker = yf_ticker(sym)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=int(years*365.25))
    step_days = 50 if tf=="15m" else (365 if tf=="1h" else 365*5)
    parts=[]
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=step_days), end)
        df = yf.download(tickers=ticker, interval=itv, start=cur, end=nxt, progress=False, prepost=False)
        if df is not None and not df.empty:
            df = df.rename(columns={
                "Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume"
            }).reset_index()
            # yfinance antaa Timestamp kolumnin nimellä Datetime/DatetimeUTC
            time_col = "Datetime" if "Datetime" in df.columns else ("Date" if "Date" in df.columns else df.columns[0])
            df["time"] = pd.to_datetime(df[time_col], utc=True).astype("int64")//10**6
            df = df[["time","open","high","low","close","volume"]]
            parts.append(df)
        cur = nxt
        time.sleep(0.2)
    if not parts:
        raise RuntimeError("no data from yfinance")
    df = pd.concat(parts, ignore_index=True).drop_duplicates(subset=["time"]).sort_values("time")
    write_parquet(os.path.join(OUT, f"{sym}_{tf}.parquet"), df)
    return len(df)

def backfill_one(sym:str, tf:str, years:int):
    if is_crypto(sym):
        try:
            rows = fetch_crypto_ccxt(sym, tf, years)
            return {"sym":sym,"tf":tf,"rows":rows,"src":"binance"}
        except Exception as e:
            # fallback yf jos mahdollista
            try:
                rows = fetch_yf(sym, tf, years)
                return {"sym":sym,"tf":tf,"rows":rows,"src":"yfinance_fallback"}
            except Exception as e2:
                return {"sym":sym,"tf":tf,"err":str(e2)}
    else:
        try:
            rows = fetch_yf(sym, tf, years)
            return {"sym":sym,"tf":tf,"rows":rows,"src":"yfinance"}
        except Exception as e:
            return {"sym":sym,"tf":tf,"err":str(e)}

if __name__=="__main__":
    sym, tf, years = sys.argv[1], sys.argv[2], int(sys.argv[3])
    print(json.dumps(backfill_one(sym,tf,years)))
