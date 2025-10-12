import os, sys, requests, json

API = "https://api-capital.backend-capital.com"
ID  = os.getenv("CAPITAL_LOGIN")
PWD = os.getenv("CAPITAL_PASSWORD")
KEY = os.getenv("CAPITAL_API_KEY")

def session():
    if not all([ID, PWD, KEY]):
        raise SystemExit("Puuttuu CAPITAL_* env-muuttujia")
    h = {"X-CAP-API-KEY": KEY, "Content-Type": "application/json"}
    r = requests.post(f"{API}/api/v1/session", headers=h, json={"identifier": ID, "password": PWD})
    r.raise_for_status()
    h.update({"CST": r.headers["CST"], "X-SECURITY-TOKEN": r.headers["X-SECURITY-TOKEN"]})
    return h

def epic_for(h, term: str) -> str:
    r = requests.get(f"{API}/api/v1/markets", headers=h, params={"searchTerm": term})
    r.raise_for_status()
    markets = r.json().get("markets", [])
    if not markets:
        raise SystemExit(f"Ei markkinoita termillä {term}")
    termu = term.upper().replace("/", "")
    # paras osuma: nimen alku vastaa termiä
    for m in markets:
        nm = (m.get("instrumentName") or "").upper().replace("/", "")
        if nm.startswith(termu):
            return m["epic"]
    return markets[0]["epic"]

def details(h, epic: str) -> dict:
    r = requests.get(f"{API}/api/v1/markets/{epic}", headers=h)
    r.raise_for_status()
    j = r.json()
    inst = j.get("instrument", {})
    rules = j.get("dealingRules", {})

    # min koko
    mds = rules.get("minDealSize")
    if isinstance(mds, dict):
        min_size = float(mds.get("value") or 0)
    else:
        min_size = float(mds or 0)

    # askel / lot koko
    step = float(inst.get("lotSize") or 1)

    # valuutta
    currs = inst.get("currencies") or [{"code": "USD"}]
    currency = currs[0].get("code", "USD")

    # margin/leverage (eri markkinoilla eri kentät)
    margin_rate = None
    lev = None
    bands = inst.get("marginDepositBands") or []
    if bands:
        try:
            margin_rate = float(bands[0]["marginRate"])
        except Exception:
            pass
    if not margin_rate:
        # joillain markkinoilla voi olla "marginRate" suoraan
        try:
            margin_rate = float(inst.get("marginRate"))
        except Exception:
            pass
    if not margin_rate:
        # spread bet/crypto: joskus "leverage" annetaan suoraan
        try:
            lev = float(inst.get("leverage"))
        except Exception:
            lev = None
    if (lev is None) and margin_rate:
        lev = 1.0 / margin_rate if margin_rate else None

    name = (inst.get("name") or "").replace("/", "")

    return {
        "symbol": name or epic,
        "epic": epic,
        "min_size": min_size,
        "step": step,
        "currency": currency,
        "margin_rate": margin_rate,
        "leverage": round(lev, 2) if isinstance(lev, (int, float)) and lev > 0 else None,
    }

if __name__ == "__main__":
    syms = sys.argv[1:] or ["EURUSD","GBPUSD","BTCUSDT","ETHUSDT","XRPUSDT","SOLUSDT","ADAUSDT"]
    h = session()
    out = []
    for s in syms:
        e = epic_for(h, s)
        d = details(h, e)
        out.append(d)
        print(f"[SPEC] {s} epic={e} min={d['min_size']} step={d['step']} lev={d['leverage']} marginRate={d['margin_rate']}")
    os.makedirs("data", exist_ok=True)
    with open("data/broker_specs.json","w") as f:
        json.dump(out, f, indent=2)
