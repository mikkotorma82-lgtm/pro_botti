#!/usr/bin/env python3
import os, json, requests, sys, pathlib

API = "https://api-capital.backend-capital.com"

# --- Täydennä tarvittaessa oman tilisi epicit ---
EPIC = {
  "EURUSD":  "CS.D.EURUSD.CFD.IP",
  "GBPUSD":  "CS.D.GBPUSD.CFD.IP",
  "US500":   "IX.D.SPTRD.DAILY.IP",     # S&P 500 cash/rolling; vaihda omaan jos eri
  "US100":   "IX.D.NASDAQ.CASH.IP",     # NAS100 cash/rolling
  "AAPL":    "UA.D.AAPL.CFD.IP",
  "NVDA":    "UA.D.NVDA.CFD.IP",
  "TSLA":    "UA.D.TSLA.CFD.IP",
  "BTCUSDT": "CS.D.BITCOIN.CFD.IP",     # bitcoin/usd CFD
  "ETHUSDT": "CS.D.ETHUSD.CFD.IP",
  "XRPUSDT": "CS.D.XRPUSD.CFD.IP",
  "SOLUSDT": "CS.D.SOLUSD.CFD.IP",
  "ADAUSDT": "CS.D.ADAUSD.CFD.IP",
}

def envget():
    E={}
    if os.path.exists("botti.env"):
        for ln in open("botti.env",encoding="utf-8"):
            if "=" in ln:
                k,v=ln.strip().split("=",1); E[k]=v
    return {
      "KEY":   os.getenv("CAPITAL_API_KEY")  or E.get("CAPITAL_API_KEY",""),
      "LOGIN": os.getenv("CAPITAL_LOGIN")    or E.get("CAPITAL_LOGIN",""),
      "PASS":  os.getenv("CAPITAL_PASSWORD") or E.get("CAPITAL_PASSWORD",""),
    }

def sess(KEY, LOGIN, PASS):
    s=requests.Session()
    s.headers.update({"X-CAP-API-KEY": KEY, "Accept":"application/json","Content-Type":"application/json"})
    r=s.post(API+"/api/v1/session", json={"identifier": LOGIN, "password": PASS}, timeout=20)
    r.raise_for_status()
    s.headers.update({"CST": r.headers.get("CST",""), "X-SECURITY-TOKEN": r.headers.get("X-SECURITY-TOKEN","")})
    return s

def fetch_market(s, epic):
    r=s.get(API+f"/api/v1/markets/{epic}", timeout=20)
    r.raise_for_status()
    m=r.json().get("instrument") or r.json()
    dr=m.get("dealingRules") or {}
    minsz=dr.get("minDealSize") or dr.get("minSize") or 0
    step =(dr.get("minStep") or m.get("lotSize") or m.get("increment") or 1)
    # leverage: jos marginaaliprosentti esim. 3.33 -> 30:1
    lev=None
    mar=dr.get("marginRequirement") or m.get("marginRequirement")
    try:
        if mar: lev = round(100.0/float(mar))
        elif "leverage" in m: lev=float(m["leverage"])
    except Exception:
        lev=None
    return {
        "epic": epic,
        "name": m.get("name") or m.get("instrumentName") or epic,
        "currency": m.get("currency") or "USD",
        "min_size": float(minsz or 0),
        "step": float(step or 1),
        "leverage": lev
    }

def main():
    cfg=pathlib.Path("config.yaml").read_text()
    # kerää symbolilista market.symbolsista
    import re
    ms=re.search(r'(?m)^market:\s*\n(?:[^\n]*\n)*?\s*symbols:\s*\[([^\]]+)\]', cfg)
    symbols=[x.strip() for x in (ms.group(1).split(",") if ms else []) if x.strip()]
    if not symbols:
        symbols=list(EPIC.keys())

    env=envget()
    if not all(env.values()):
        print("ERROR: CAPITAL_* asetukset puuttuvat botti.env:stä", file=sys.stderr); sys.exit(2)
    s=sess(env["KEY"], env["LOGIN"], env["PASS"])

    rows=[]
    for sym in symbols:
        epic=EPIC.get(sym)
        if not epic:
            rows.append({"symbol":sym,"error":"no_epic_mapping"}); continue
        try:
            info=fetch_market(s, epic)
            rows.append({"symbol":sym, **info})
        except requests.HTTPError as e:
            rows.append({"symbol":sym,"epic":epic,"error":f"http {e.response.status_code}"})
    pathlib.Path("data").mkdir(exist_ok=True)
    with open("data/broker_specs.json","w",encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)

    for r in rows:
        if "error" in r:
            print(f"{r['symbol']:<8} - {r.get('error')}")
        else:
            lev=r['leverage'] if r['leverage'] is not None else "-"
            print(f"{r['symbol']:<8} min={r['min_size']} step={r['step']} lev={lev} cur={r['currency']}  ({r['epic']})")
            print(f"[SIZE] {r['symbol']} min={r['min_size']} step={r['step']} currency={r['currency']} leverage={lev}")
if __name__=="__main__": main()
