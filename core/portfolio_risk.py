import pandas as pd, numpy as np, os, json, time
from datetime import datetime

DATA_DIR="data/history"
OUT="data/portfolio_risk.json"

def calc_corr(symbols,tf="1h"):
    dfs=[]
    for s in symbols:
        p=f"{DATA_DIR}/{s}/{tf}.csv"
        if not os.path.exists(p): continue
        d=pd.read_csv(p)
        if "close" not in d: continue
        d=d[["timestamp","close"]].tail(1000)
        d["ret"]=d["close"].pct_change()
        d["time"]=pd.to_datetime(d["timestamp"],unit="ms")
        d=d.set_index("time")["ret"]
        dfs.append(d.rename(s))
    if not dfs: return {}
    df=pd.concat(dfs,axis=1).dropna()
    corr=df.corr()
    vol=df.std()
    var=df.var()
    risk=(df*df).mean()**0.5
    m={"timestamp":int(time.time()),"symbols":symbols,
       "corr":corr.to_dict(),"vol":vol.to_dict(),"var":var.to_dict(),"risk":risk.to_dict()}
    os.makedirs("data",exist_ok=True)
    with open(OUT,"w") as f: json.dump(m,f,indent=2)
    print(f"[RISK] updated {len(symbols)} symbols -> {OUT}")

if __name__=="__main__":
    # quick test
    syms=[]
    for r,_,fs in os.walk(DATA_DIR):
        for f in fs:
            if f.endswith(".csv"): syms.append(r.split("/")[-1]); break
    calc_corr(syms)
