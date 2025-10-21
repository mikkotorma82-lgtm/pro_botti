import sys, time, os, json, re
import pandas as pd
import ccxt

def norm_unified(sym: str):
    if '/' in sym: 
        return sym
    m = re.match(r'^([A-Z]+?)(USDT|USD|EUR|GBP)$', sym)
    return f'{m.group(1)}/{m.group(2)}' if m else sym

if len(sys.argv) < 4:
    print("usage: backfill_ccxt.py SYMBOL TF LIMIT", flush=True); sys.exit(1)

raw_sym, tf, limit = sys.argv[1], sys.argv[2], int(sys.argv[3])
ex = ccxt.binance({'enableRateLimit': True})
sym = norm_unified(raw_sym)
m = ex.load_markets()
if sym not in m:
    print(json.dumps({"ok":False,"why":"symbol_not_supported","sym":sym})); sys.exit(0)

tf_map = {"15m":"15m","1h":"1h","4h":"4h"}
if tf not in tf_map:
    print(json.dumps({"ok":False,"why":"tf_not_supported","tf":tf})); sys.exit(1)

ms = ex.parse_timeframe(tf_map[tf]) * 1000
since = ex.milliseconds() - limit*ms

data = []
while True:
    ohlcv = ex.fetch_ohlcv(sym, tf_map[tf], since=since, limit=1000)
    if not ohlcv: break
    data += ohlcv
    since = ohlcv[-1][0] + ms
    if len(ohlcv) < 1000: break
    time.sleep(ex.rateLimit/1000.0)

if not data:
    print(json.dumps({"ok":False,"why":"no_rows"})); sys.exit(0)

df = pd.DataFrame(data, columns=["time","open","high","low","close","volume"])
# Varmista tyypit ja järjestys
df["time"] = df["time"].astype("int64")
df = df.sort_values("time").drop_duplicates("time")

os.makedirs("data/history", exist_ok=True)
out = f"data/history/{raw_sym.replace('/','')}_{tf}.parquet"
df.to_parquet(out, index=False)
print(json.dumps({"ok":True,"rows":len(df),"file":out}))
