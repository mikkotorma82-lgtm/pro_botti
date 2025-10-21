from __future__ import annotations
import os, json, time
from pathlib import Path
from datetime import datetime, timezone
from typing import Tuple, Set

# dotenv on ok jos löytyy
try:
    from tools._dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from tools.util_http import req

# BASE valitaan envistä; live-ympäristössä tämän pitäisi olla api-capital...
BASE = (os.getenv("CAPITAL_API_BASE") or os.getenv("CAPITAL_BASE_URL") or "https://demo-api-capital.backend-capital.com").rstrip("/")
API  = BASE + "/api/v1"

# Välimuistit
ECACHE = Path("/root/pro_botti/data/epic_cache.json")
RCACHE = Path("/root/pro_botti/data/rules_cache.json")
ECACHE.parent.mkdir(parents=True, exist_ok=True)
_epic  = json.loads(ECACHE.read_text())  if ECACHE.exists() else {}
_rules = json.loads(RCACHE.read_text())  if RCACHE.exists() else {}

def _save():
    ECACHE.write_text(json.dumps(_epic,  indent=2, ensure_ascii=False))
    RCACHE.write_text(json.dumps(_rules, indent=2, ensure_ascii=False))

def _headers(tok: dict | None = None):
    # Capital.com headerit; lisää Content-Type ettei /session anna 400:aa
    h = {
        "X-CAP-API-KEY": os.getenv("CAPITAL_API_KEY") or os.getenv("CAPITAL_KEY",""),
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if tok:
        h["CST"] = tok.get("CST","")
        h["X-SECURITY-TOKEN"] = tok.get("X-SECURITY-TOKEN","")
    return h

def login() -> dict:
    # Käytä samoja env-nimiä kuin live_daemon näyttää: identifier/login + password
    identifier = (
        os.getenv("CAPITAL_IDENTIFIER")
        or os.getenv("CAPITAL_USERNAME")
        or os.getenv("CAPITAL_LOGIN")
    )
    password  = os.getenv("CAPITAL_PASSWORD")
    if not identifier or not password:
        raise RuntimeError("CAPITAL_IDENTIFIER/USERNAME/LOGIN tai CAPITAL_PASSWORD puuttuu ympäristöstä")

    r = req(
        "POST",
        API + "/session",
        headers=_headers(),
        json={"identifier": identifier, "password": password, "encryptedPassword": False},
    )
    return {
        "CST": r.headers.get("CST",""),
        "X-SECURITY-TOKEN": r.headers.get("X-SECURITY-TOKEN",""),
    }

# Tunnetut aliaset ja kryptolistat
_ALIASES = {
  "US500":["US 500","S&P 500","SPX"],
  "US100":["US 100","NASDAQ 100","NDX","NAS100"],
  "US30":["US 30","Dow Jones","DJI"],
  "GER40":["Germany 40","DAX","DE40"],
  "FRA40":["France 40","CAC40"],
  "UK100":["FTSE 100","FTSE"],
  "EU50":["Euro Stoxx 50","SX5E"],
  "JPN225":["Japan 225","Nikkei 225","NKY"],
  "HK50":["Hong Kong 50","HSI"],
  "AUS200":["Australia 200","ASX 200","AS51"],
}
_KNOWN_CRYPTO = {"BTC","ETH","XRP","SOL","ADA","DOGE","BNB","LTC","SHIB","AVAX","DOT","MATIC","LINK","TRX","XLM","APT","SUI"}

def _canon(symbol: str) -> str:
    s = symbol.upper().strip()
    # …USDT -> …USD (esim. ADAUSDT -> ADAUSD)
    if s.endswith("USDT"):
        s = s[:-4] + "USD"
    return s

def _class_sets(sym: str) -> Tuple[Set[str], Set[str]]:
    s = sym.upper()
    if any(s == c + "USD" for c in _KNOWN_CRYPTO):
        return {"CRYPTO","CRYPTOCURRENCIES"}, {"CRYPTO","CRYPTOCURRENCIES"}
    if len(s) == 6 and s.isalpha():  # klassinen FX-pari
        return {"CURRENCIES","FX"}, {"CURRENCIES","FX"}
    if s in _ALIASES or s.startswith(("US","GER","FRA","UK","EU","JPN","HK","AUS")):
        return {"INDICES","INDEX"}, {"INDICES","INDEX"}
    if s in {"XAUUSD","XAGUSD","WTI","BRENT","NATGAS","OIL","OIL_CRUDE"}:
        return {"COMMODITIES","COMMODITY"}, {"COMMODITIES","COMMODITY"}
    return {"SHARES","EQUITIES"}, {"SHARES","EQUITIES"}

def _rank(hit: dict, s: str, itypes: Set[str], mtypes: Set[str]) -> int:
    score = 0
    ep  = (hit.get("epic") or "").upper()
    it  = (hit.get("instrumentType") or "").upper()
    mt  = (hit.get("marketType") or "").upper()
    sym = (hit.get("symbol") or "").upper().replace(" ","")
    nm  = (hit.get("instrumentName") or "").upper().replace(" ","")
    exp = (hit.get("expiry") or "-")
    stat= (hit.get("marketStatus") or "").upper()

    if it in itypes: score += 6
    if mt in mtypes: score += 2
    if exp == "-":   score += 4

    # FX/CRYPTO: älä valitse futuuria
    if (len(s)==6 and s.isalpha()) or any(s == c+"USD" for c in _KNOWN_CRYPTO):
        if exp != "-": score -= 100

    if s == sym or s == nm: score += 6
    if ".CASH." in ep or ".SPOT." in ep or ".CFD." in ep: score += 2
    if ep.endswith(".IP"): score += 2
    if stat == "TRADEABLE": score += 1
    return score

def resolve_epic(symbol: str, tok: dict) -> tuple[str, dict]:
    raw = symbol.upper()
    s = _canon(raw)
    # Käytä cachea alkuperäisellä pyynnöllä
    if raw in _epic:
        x = _epic[raw]
        return x["epic"], x["hit"]

    itypes, mtypes = _class_sets(s)
    terms = [s] + _ALIASES.get(s, [])

    # Kryptolle lisää termejä
    if any(s == c+"USD" for c in _KNOWN_CRYPTO):
        c = s[:-3]
        terms += [f"{c}/USD", f"{c} USD", c]

    candidates, seen = [], set()
    for term in dict.fromkeys(terms):  # uniq
        r = req("GET", API + "/markets", headers=_headers(tok), params={"searchTerm": term})
        for h in r.json().get("markets", []) or []:
            ep = h.get("epic")
            if not ep or ep in seen: 
                continue
            seen.add(ep)
            candidates.append(h)

    if not candidates:
        raise RuntimeError(f"EPIC not found for {raw} (canon {s})")

    # väärä asset-luokka pois
    filt = [h for h in candidates if (h.get("instrumentType") or "").upper() in itypes]
    if filt:
        candidates = filt

    # suositaan spot/cash
    spot = [h for h in candidates if (h.get("expiry") or "-") == "-"]
    if spot:
        candidates = spot

    ranked = sorted(candidates, key=lambda x: _rank(x, s, itypes, mtypes), reverse=True)
    hit = ranked[0]
    _epic[raw] = {"epic": hit["epic"], "hit": hit}
    _save()
    return hit["epic"], hit

def market_rules(epic: str, tok: dict) -> dict:
    if epic in _rules:
        return _rules[epic]
    md = req("GET", API + f"/markets/{epic}", headers=_headers(tok)).json()
    dr = md.get("dealingRules") or {}
    snap = md.get("snapshot") or {}
    inst = md.get("instrument") or {}
    itype = inst.get("type") or inst.get("instrumentType","")
    rules = {
        "min_size": float((dr.get("minDealSize") or {}).get("value") or 0),
        "step": float((dr.get("minDealSizeFractional") or {}).get("value") or 1.0),
        "lot_size": float(inst.get("lotSize") or 1.0),
        "currency": snap.get("currency") or "USD",
        "instrumentType": itype,
        "marketStatus": (snap.get("marketStatus") or ""),
    }
    if rules["step"] <= 0: rules["step"] = 1.0
    _rules[epic] = rules
    _save()
    return rules

def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms/1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

def _resolution(tf: str) -> str:
    tf = tf.lower()
    return {"15m":"MINUTE_15","1h":"HOUR","4h":"HOUR_4"}.get(tf, "HOUR")

def prices(symbol: str, tf: str, start_epoch_ms: int | None, end_epoch_ms: int | None) -> list[dict]:
    tok = login()
    epic, _ = resolve_epic(symbol, tok)
    res = _resolution(tf)
    out = []; page = 0
    while True:
        params = {"resolution": res, "pageSize": 200}
        if start_epoch_ms: params["from"] = _iso(start_epoch_ms)
        if end_epoch_ms:   params["to"]   = _iso(end_epoch_ms)
        if page:           params["pageNumber"] = page
        r = req("GET", API + f"/prices/{epic}", headers=_headers(tok), params=params)
        js = r.json()
        cs = js.get("prices") or js.get("candles") or []
        for c in cs:
            t = c.get("snapshotTimeUTC") or c.get("snapshotTime") or c.get("date")
            o = c.get("openPrice") or c.get("open") or {}; h = c.get("highPrice") or c.get("high") or {}
            l = c.get("lowPrice")  or c.get("low")  or {}; cl= c.get("closePrice") or c.get("close") or {}
            v = c.get("lastTradedVolume") or c.get("volume") or 0
            def val(x):
                if isinstance(x, dict):
                    return x.get("mid", x.get("bid", x.get("ask", None)))
                return x
            out.append({"ts": t, "open": val(o), "high": val(h), "low": val(l), "close": val(cl), "volume": v})
        pd = (js.get("metadata") or {}).get("pageData") or {}
        if not pd or pd.get("pageNumber", 0) >= pd.get("totalPages", 0):
            break
        page += 1
        time.sleep(0.05)
    return out
