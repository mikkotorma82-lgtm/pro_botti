import os
import requests
from tools import epic_resolver

def get_bid_ask(symbol: str, sess=None, base=None):
    """
    Palauttaa (bid, ask) Capital.com API:sta annetulle symbolille.
    Käyttää epic_resolver.resolve_epic() hakeakseen EPIC-koodin.
    """
    try:
        sym = (symbol or "").upper()
        epic = epic_resolver.resolve_epic(sym)
        base = base or os.getenv("CAPITAL_API_BASE")
        if not base or not sess:
            # hae sessio ja base jos ei annettu
            sess2, base2 = capital_rest_login()
            base = base or base2
            sess = sess or sess2

        if not sess:
            from tools import provider_capital
            sess = provider_capital.capital_session()

        hdr = dict(getattr(sess, "headers", {}))
        hdr.setdefault("Accept", "application/json")
        hdr.setdefault("Content-Type", "application/json")
        hdr["VERSION"] = "3"

        url = f"{base.rstrip('/')}/api/v1/prices/{epic}?resolution=MINUTE&max=1"
        r = sess.get(url, headers=hdr, timeout=10)
        r.raise_for_status()
        js = r.json() or {}
        arr = js.get("prices") or js.get("content") or []
        if not arr:
            return None

        p = arr[-1]
        bid = p.get("bid") or (p.get("closePrice", {}) or {}).get("bid")
        ask = p.get("ask") or (p.get("closePrice", {}) or {}).get("ask")

        if bid is None or ask is None:
            return None
        return (float(bid), float(ask))

    except Exception as e:
        print(f"[WARN] get_bid_ask({symbol}) failed: {e}")
        return None


def capital_rest_login(force=False):
    """Kirjaudu Capital.com RESTiin käyttäen env-arvoja:
    CAPITAL_API_BASE, CAPITAL_API_KEY, CAPITAL_USERNAME, CAPITAL_PASSWORD, CAPITAL_ACCOUNT_TYPE
    Palauttaa: (requests.Session, base_url)
    """
    import os, requests
    base = os.getenv("CAPITAL_API_BASE")
    api_key = os.getenv("CAPITAL_API_KEY")
    user = os.getenv("CAPITAL_USERNAME")
    pwd = os.getenv("CAPITAL_PASSWORD")
    acc_type = (os.getenv("CAPITAL_ACCOUNT_TYPE") or "LIVE").upper()  # LIVE tai DEMO

    if not all([base, api_key, user, pwd]):
        raise RuntimeError("Missing CAPITAL_* envs for login")

    sess = requests.Session()
    hdr = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-CAP-API-KEY": api_key,
        "VERSION": "3",
        "X-IG-API-KEY": api_key,  # Capital/IG backend käyttää tätä nimikettä
    }
    payload = {
        "identifier": user,
        "password":   pwd,
        "encryptedPassword": False,
    }
    # Kirjaudu
    r = sess.post(f"{base.rstrip('/')}/api/v1/session", json=payload, headers=hdr, timeout=15)
    r.raise_for_status()

    # Poimi tokenit headerista
    cst = r.headers.get("CST") or r.headers.get("cst")
    sec = r.headers.get("X-SECURITY-TOKEN") or r.headers.get("x-security-token")
    if not cst or not sec:
        raise RuntimeError("Login succeeded but missing CST/X-SECURITY-TOKEN")

    # Aseta oletusheaderit sessioon
    sess.headers.update({
        "Accept": "application/json",
        "Content-Type": "application/json",
        "VERSION": "3",
        "X-CAP-API-KEY": api_key,
        "X-IG-API-KEY": api_key,
        "CST": cst,
        "X-SECURITY-TOKEN": sec,
    })

    # Vaihda tilityyppi (DEMO/LIVE) jos API sitä tukee — Capitalissa se on asetuksissa,
    # mutta jos päätepiste vaatii, lisäheaderi:
    sess.headers.setdefault("IG-ACCOUNT-TYPE", acc_type)

    return sess, base
