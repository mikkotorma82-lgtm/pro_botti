import os, sys, json, subprocess, concurrent.futures as cf
ROOT = "/root/pro_botti"; PYEXE = f"{ROOT}/venv/bin/python"; HIST = f"{ROOT}/data/history"
ccxt_syms = ["BTCUSDT","ETHUSDT","ADAUSDT","SOLUSDT","XRPUSDT"]
yf_syms   = ["AAPL","NVDA","TSLA","US100","US500","EURUSD","GBPUSD","BTCUSD","ETHUSD"]
tfs       = ["15m","1h","4h"]

def run(cmd):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out,_ = p.communicate(); return p.returncode, out

def need(sym, tf): 
    return not os.path.exists(f"{HIST}/{sym}_{tf}.parquet")

def task_ccxt(sym, tf, lim="200000"):
    if not need(sym, tf): return {"ok":True,"sym":sym,"tf":tf,"why":"exists"}
    rc, out = run([PYEXE, f"{ROOT}/tools/backfill_ccxt.py", sym, tf, lim])
    try: return json.loads(out.strip().splitlines()[-1])
    except: return {"ok":False,"sym":sym,"tf":tf,"raw":out}

def task_yf(sym, tf):
    if not need(sym, tf): return {"ok":True,"sym":sym,"tf":tf,"why":"exists"}
    rc, out = run([PYEXE, f"{ROOT}/tools/backfill_yf.py", sym, tf])
    try: return json.loads(out.strip().splitlines()[-1])
    except: return {"ok":False,"sym":sym,"tf":tf,"raw":out}

if __name__=="__main__":
    os.makedirs(HIST, exist_ok=True)
    jobs=[]
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        # Kryptot ccxt
        for s in ccxt_syms:
            for tf in tfs: jobs.append(ex.submit(task_ccxt, s, tf))
        # YF: muut; BTCUSD/ETHUSD vain 4h YF:ltä, intrat proxyllä CCXT:stä
        for s in yf_syms:
            for tf in tfs:
                if s in ("BTCUSD","ETHUSD") and tf!="4h":
                    proxy = "BTCUSDT" if s=="BTCUSD" else "ETHUSDT"
                    jobs.append(ex.submit(task_ccxt, proxy, tf))
                else:
                    jobs.append(ex.submit(task_yf, s, tf))
        for f in cf.as_completed(jobs):
            print(json.dumps(f.result()), flush=True)
