#!/usr/bin/env python3
from __future__ import annotations
import os
import time
from typing import Any, Dict, Optional, Tuple

import requests


# Ympäristömuuttujat:
# - CAPITAL_API_BASE=https://api-capital.backend-capital.com
# - CAPITAL_API_KEY=...
# - CAPITAL_USERNAME=...
# - CAPITAL_PASSWORD=...
# (valinnainen) CAPITAL_ACCOUNT_TYPE=CFD
#
# EPIC-yliasetukset (valinnainen):
# - CAPITAL_EPIC_US500=US SPX 500
# - CAPITAL_EPIC_EURUSD=EUR/USD
# jne. (muoto vapaa, katso _resolve_epic)
#
# AUTH CONTRACT:
# - POST {BASE}/api/v1/session
#   Headers: X-CAP-API-KEY, Accept: application/json, Content-Type: application/json
#   Body: {"identifier": USERNAME, "password": PASSWORD}
# - Lue session headerit: CST, X-SECURITY-TOKEN
# - Lisää nämä kaikkiin jatkokutsuihin
# - Älä käytä TOTP:ia (jos palvelin vaatii, nosta virhe)
# - Kätke istunto prosessin ajaksi -> älä kirjautuile jokaisella pyynnöllä
#
# Hinnat:
# - GET {BASE}/api/v1/prices/{EPIC}?resolution=MINUTE&max=1
#   Headers: X-CAP-API-KEY, CST, X-SECURITY-TOKEN


_CAPITAL_SESS: Optional[requests.Session] = None
_CAPITAL_BASE: Optional[str] = None
_CAPITAL_LAST_LOGIN_TS: float = 0.0
_CAPITAL_LOGIN_TTL: int = int(os.getenv("CAPITAL_LOGIN_TTL", "540"))  # ~9 min (token ~10 min)


def _mandatory_env(key: str) -> str:
    v = os.getenv(key)
    if not v:
        raise RuntimeError(f"Missing {key} env")
    return v


def _resolve_epic(symbol: str) -> str:
    """
    EPIC-resolutionti:
    - CAPITAL_EPIC_<UPPER_ALNUM> yliajaa (esim. CAPITAL_EPIC_US500="US SPX 500")
    - Muuten palautetaan symbol sellaisenaan (Capitalissa moni toimii suoraan: "US SPX 500","EUR/USD","GOLD","AAPL","BTC/USD")
    """
    # Normalisoi nimen perusmuoto ympäristöavaimen tekemiseksi
    key = "CAPITAL_EPIC_" + "".join(ch for ch in symbol.upper() if ch.isalnum())
    return os.getenv(key, symbol)


def _ensure_session_headers(s: requests.Session, cst: str, xsec: str, account_type: Optional[str]) -> None:
    s.headers.update({
        "Accept": "application/json",
        "Content-Type": "application/json",
        "CST": cst,
        "X-SECURITY-TOKEN": xsec,
    })
    if account_type:
        s.headers.setdefault("X-CAP-ACCOUNT-TYPE", account_type)


def capital_rest_login(force: bool = False) -> Tuple[requests.Session, str]:
    """
    Luo/käytä Capital LIVE REST -istuntoa ja palauta (session, base_url).
    - Ei TOTP:ia. Jos backend vaatii TOTP:n, nostetaan virhe.
    - Vältä 429:ää: kätke istunto prosessin ajaksi; älä loggaa sisään jokaisessa pyynnössä.
    """
    global _CAPITAL_SESS, _CAPITAL_BASE, _CAPITAL_LAST_LOGIN_TS

    now = time.time()
    if (not force) and _CAPITAL_SESS is not None and (now - _CAPITAL_LAST_LOGIN_TS < _CAPITAL_LOGIN_TTL):
        return _CAPITAL_SESS, _CAPITAL_BASE  # type: ignore[return-value]

    base = _mandatory_env("CAPITAL_API_BASE").rstrip("/")
    api_key = _mandatory_env("CAPITAL_API_KEY")
    username = _mandatory_env("CAPITAL_USERNAME")
    password = _mandatory_env("CAPITAL_PASSWORD")
    account_type = os.getenv("CAPITAL_ACCOUNT_TYPE", "CFD")

    s = requests.Session()
    s.headers.update({
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-CAP-API-KEY": api_key,
        "User-Agent": "pro-botti/1.0 (+https://github.com/mikkotorma82-lgtm/pro_botti)"
    })

    url = f"{base}/api/v1/session"
    payload: Dict[str, Any] = {
        "identifier": username,
        "password": password,
        # "encryptedPassword": False,  # ei pakollinen; backend hyväksyy ilmankin
    }

    # Yritä muutama kerta; jos 429, tee kevyt backoff
    last_err = None
    for attempt in range(3):
        r = s.post(url, json=payload, timeout=20)
        if r.status_code == 429:
            time.sleep(1.5 * (attempt + 1))
            last_err = {"status": r.status_code, "text": r.text[:200]}
            continue

        if r.status_code in (200, 201):
            cst = r.headers.get("CST")
            xsec = r.headers.get("X-SECURITY-TOKEN")

            # Joissakin asennuksissa tokenit voivat tulla myös bodysta – kokeile lukea
            if not cst or not xsec:
                try:
                    data = r.json()
                    cst = cst or data.get("CST")
                    xsec = xsec or data.get("X-SECURITY-TOKEN")
                except Exception:
                    pass

            if not cst or not xsec:
                raise RuntimeError("Capital login OK but missing CST/X-SECURITY-TOKEN")

            _ensure_session_headers(s, cst, xsec, account_type)
            _CAPITAL_SESS = s
            _CAPITAL_BASE = base
            _CAPITAL_LAST_LOGIN_TS = time.time()
            return _CAPITAL_SESS, _CAPITAL_BASE

        if r.status_code in (401, 403):
            # Yleensä: TOTP pakotettu tai tunnukset/avain väärin
            try:
                err = r.json()
            except Exception:
                err = {"body": r.text}
            raise RuntimeError(
                f"Capital login failed ({r.status_code}). "
                f"Server may enforce TOTP for this API key/tenant. Response: {err}"
            )

        # Muu virhe -> ylös
        last_err = {"status": r.status_code, "text": r.text[:200]}
        r.raise_for_status()

    raise RuntimeError(f"Capital login: too many 429 / unexpected errors. last={last_err}")


def capital_get_bid_ask(symbol: str) -> Optional[Tuple[float, float]]:
    """
    Hakee viimeisimmän bid/ask-parin Capital RESTiltä (MINUTE, max=1).
    symbol -> resolvoituu EPICiksi _resolve_epic()-kutsulla.
    """
    sess, base = capital_rest_login()
    epic = _resolve_epic(symbol)
    url = f"{base}/api/v1/prices/{epic}"
    params = {"resolution": "MINUTE", "max": 1}
    r = sess.get(url, params=params, timeout=15)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    data = r.json()

    bid = ask = None
    try:
        # Capital/IG-tyylinen 'prices' lista
        arr = data.get("prices") or data.get("data") or []
        if arr:
            last = arr[-1]
            bid = last.get("bid")
            ask = last.get("ask")
            # Jos rakenne on candle-tyylinen (o/h/l/c), näitä ei välttämättä ole -> palauta None
    except Exception:
        pass

    if isinstance(bid, (int, float)) and isinstance(ask, (int, float)):
        return float(bid), float(ask)
    return None


def capital_get_candles(symbol: str, tf: str, max_rows: int = 500) -> Optional[list[dict]]:
    """
    Hakee OHLCV-kynttilät (data-rakenne sellaisenaan).
    Suositus on käyttää tähän erillistä /history/candles -endpointtia, mutta
    tässä referenssissä pidetään esimerkki lyhyenä ja käytetään tarvittaessa /prices -polkua.
    """
    sess, base = capital_rest_login()
    epic = _resolve_epic(symbol)
    # Yksinkertainen mappi; säädä tarpeen mukaan
    res_map = {"15m": "MINUTE_15", "1h": "HOUR", "4h": "HOUR_4", "1d": "DAY"}
    res = res_map.get(tf.lower(), "HOUR")
    url = f"{base}/api/v1/prices/{epic}"
    params = {"resolution": res, "max": int(max_rows)}
    r = sess.get(url, params=params, timeout=20)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    data = r.json()
    # Palauta 'prices' sellaisenaan; sovitus jätetään kutsujalle
    return data.get("prices") or data.get("data") or []
