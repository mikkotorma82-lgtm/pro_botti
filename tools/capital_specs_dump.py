#!/usr/bin/env python3
import os, re, json, requests, pathlib, sys

API = "https://api-capital.backend-capital.com"

def load_env(fn="botti.env"):
    env={}
    if os.path.exists(fn):
        for ln in open(fn,encoding="utf-8"):
            m=re.match(r'\s*([A-Za-z0-9_]+)=(.*)\s*$', ln)
            if m: env[m.group(1)] = m.group(2).strip()
    return env

E = load_env()
KEY   = os.getenv("CAPITAL_API_KEY")   or E.get("CAPITAL_API_KEY","")
LOGIN = os.getenv("CAPITAL_LOGIN")     or E.get("CAPITAL_LOGIN","")
PWD   = os.getenv("CAPITAL_PASSWORD")  or E.get("CAPITAL_PASSWORD","")

def sess():
    s=requests.Session()
    s.headers.update({"X-CAP-API-KEY": KEY, "Accept":"application/json","Content-Type":"application/json"})
    r=s.post(API+"/api/v1/session", json={"identifier": LOGIN, "password": PWD}, timeout=20)
    r.raise_for_status()
    s.headers.update({"CST": r.headers.get("CST",""), "X-SECURITY-TOKEN": r.headers.get("X-SECURITY-TOKEN","")})
    return s

def mklist(s):
    import re
    t=pathlib.Path("config.yaml").read_text()
    m=re.search(r'(?m)^market:\s*\n(?:[^\n]*\n)*?\s*symbols:\s*\[([^\]]+)\]', t)
    if not m: return [x.strip() for x in os.getenv("SYMS","EURUSD,GBPUSD,US500,US100").split(",")]
    return [x.strip() for x in m.group(1).split(",") if x.strip()]

def search_market(s, q):
    term=q.replace("/", " ")  # EUR/USD -> "EUR USD" haku
    r=s.get(API+"/api/v1/markets", params={"searchTerm": term}, timeout=20)
    r.raise_for_status()
    js=r.json()
    items = js.get("markets") or js.get("instruments") or []
    if not items: return None
    # valitse paras osuma
    def score(m):
        name=(m.get("instrumentName") or m.get("marketName") or "").upper()
        return (q in name) + (q.replace("/"," ") in name) + (q.replace("USDT"," USD T").replace("/"," ") in name)
    items.sort(key=score, reverse=True)
    m=items[0]
    dr = m.get("dealingRules") or {}
    # eri payload-versioissa kentät vaihtelevat – otetaan järkevät oletukset
    minsz = (dr.get("minDealSize") or m.get("minDealSize") or 1)
    step  = (dr.get("minStep")     or m.get("lotSize")    or m.get("increment") or 1)
    # marginaali prosentteina -> leverage
    margin_pct = (dr.get("marginRequirement") or m.get("marginRequirement") or None)
    lev = None
    try:
        if margin_pct and float(margin_pct) > 0:
            lev = round(100.0/float(margin_pct))
        elif "leverage" in m:
            lev = float(m.get("leverage"))
    except Exception:
        pass
    cur = m.get("currency") or m.get("settlementCurrency") or "USD"
    return {
        "symbol": q,
        "epic": m.get("epic") or m.get("symbol") or q,
        "name": m.get("instrumentName") or m.get("marketName") or q,
        "currency": cur,
        "min_size": float(minsz),
        "step": float(step),
        "leverage": lev
    }

def main():
    if not (KEY and LOGIN and PWD):
        print("ERROR: set CAPITAL_* in botti.env", file=sys.stderr); sys.exit(2)
    s=sess()
    rows=[]
    for sym in mklist(s):
        try:
            info=search_market(s, sym)
            rows.append(info if info else {"symbol":sym,"error":"not_found"})
        except requests.HTTPError as e:
            rows.append({"symbol":sym,"error":f"http {e.response.status_code}"})
    pathlib.Path("data").mkdir(exist_ok=True)
    open("data/broker_specs.json","w",encoding="utf-8").write(json.dumps(rows,indent=2,ensure_ascii=False))
    print("Kirjoitettu: data/broker_specs.json")
    for r in rows:
        if "error" in r: 
            print(f"{r['symbol']:<10}  -  -  -   NOT_FOUND"); 
        else:
            lev=r['leverage'] if r['leverage'] is not None else "-"
            print(f"{r['symbol']:<10} min={r['min_size']} step={r['step']} lev={lev} cur={r['currency']}  {r['name']}")
            print(f"[SIZE] {r['symbol']} min={r['min_size']} step={r['step']} currency={r['currency']} leverage={lev}")
if __name__=="__main__": main()
