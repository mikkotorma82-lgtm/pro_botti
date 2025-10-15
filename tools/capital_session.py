#!/usr/bin/env python3
from __future__ import annotations
import os
import time
from typing import Any, Dict, Optional, Tuple, List
import urllib.parse

import requests

# Env:
# CAPITAL_API_BASE=https://api-capital.backend-capital.com
# CAPITAL_API_KEY=...
# CAPITAL_USERNAME=...
# CAPITAL_PASSWORD=...
# (optional) CAPITAL_ACCOUNT_TYPE=CFD
# (optional) CAPITAL_LOGIN_TTL=540
#
# EPIC overrides (optional), e.g.:
# CAPITAL_EPIC_USSPX500="IX.D.SPTRD.D"
# CAPITAL_EPIC_EURUSD="CS.D.EURUSD.CFD.IP"
#
# Huom: näyttönimet ("US SPX 500","EUR/USD","GOLD") EIVÄT ole EPICeitä; hinnat/kynttilät
# haetaan EPICillä. Tämä moduli yrittää hakea EPICin hakusanalla jos annat näyttönimen.

_CAPITAL_SESS: Optional[requests.Session] = None
_CAPITAL_BASE: Optional[str] = None
_CAPITAL_LAST_LOGIN_TS: float = 0.0
_CAPITAL_LOGIN_TTL: int = int(os.getenv("CAPITAL_LOGIN_TTL", "540"))  # ~9 min

def _mandatory_env(key: str) -> str:
    v = os.getenv(key, "").strip()
    if not v:
        raise RuntimeError(f"Missing {key} env")
    return v

def _is_probably_epic(s: str) -> bool:
    # Capital/IG EPICit sisältävät pisteitä ja ovat ilman välilyöntejä, esim. "IX.D.SPTRD.D"
    return ("." in s) and (" " not in s)

def _env_epic_for(symbol: str) -> Optional[str]:
    # Yritetään hakea EPIC envistä: CAPITAL_EPIC_<UPPERALNUM>
    key = "CAPITAL_EPIC_" + "".join(ch for ch in symbol.upper() if ch.isalnum())
    return os.getenv(key)

def capital_rest_login(force: bool = False) -> Tuple[requests.Session, str]:
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
    payload: Dict[str, Any] = {"identifier": username, "password": password}

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
            if not cst or not xsec:
                # joissain vastauksissa tokenit voivat olla bodyn avaimissa
                try:
                    data = r.json()
                    cst = cst or data.get("CST")
                    xsec = xsec or data.get("X-SECURITY-TOKEN")
                except Exception:
                    pass
            if not cst or not xsec:
                raise RuntimeError("Capital login OK but missing CST/X-SECURITY-TOKEN")
            s.headers.update({"CST": cst, "X-SECURITY-TOKEN": xsec})
            if account_type:
                s.headers.setdefault("X-CAP-ACCOUNT-TYPE", account_type)
            _CAPITAL_SESS, _CAPITAL_BASE, _CAPITAL_LAST_LOGIN_TS = s, base, time.time()
            return _CAPITAL_SESS, _CAPITAL_BASE

        if r.status_code in (401, 403):
            try: err = r.json()
            except Exception: err = {"body": r.text}
            raise RuntimeError(f"Capital login failed ({r.status_code}). Response: {err}")

        last_err = {"status": r.status_code, "text": r.text[:200]}
        r.raise_for_status()

    raise RuntimeError(f"Capital login: too many 429 / unexpected errors. last={last_err}")

def capital_market_search(query: str, limit: int = 25) -> List[Dict[str, Any]]:
    """
    Hakee markkinat hakusanalla ja palauttaa listan, jossa mm. epic ja instrumentName.
    Kokeilee useampaa endpointtia, koska tenant/versio voi vaihdella.
    """
    sess, base = capital_rest_login()
    q = urllib.parse.quote(query)
    paths = [
        f"/api/v1/markets?searchTerm={q}",
        f"/markets?searchTerm={q}",
    ]
    out: List[Dict[str, Any]] = []
    for p in paths:
        url = f"{base}{p}"
        try:
            r = sess.get(url, timeout=20)
            if r.status_code // 100 != 2:
                continue
            data = r.json()
            # mahdollisia muotoja:
            # {"markets":[{"epic":"...","instrumentName":"..."}, ...]}
            # tai {"data":[...]} riippuen tenantista
            items = data.get("markets") or data.get("data") or []
            for it in items:
                d = {
                    "epic": it.get("epic") or it.get("EPIC") or it.get("id"),
                    "instrumentName": it.get("instrumentName") or it.get("name") or it.get("symbol"),
                    "raw": it
                }
                if d["epic"]:
                    out.append(d)
            if out:
                break
        except Exception:
            continue
    # rajoita
    return out[:limit]

def _resolve_epic(symbol_or_name: str) -> str:
    """
    EPIC-resoluutiojärjestys:
    1) Jos näyttää jo EPICiltä (sis. pisteitä, ei välilyöntejä) → käytä sellaisenaan
    2) Jos CAPITAL_EPIC_<UPPERALNUM> on asetettu → käytä sitä
    3) Muuten hae markkinoista hakusanalla ja valitse paras osuma
    """
    s = symbol_or_name.strip()
    if _is_probably_epic(s):
        return s

    env_epic = _env_epic_for(s)
    if env_epic:
        return env_epic.strip()

    # Haku
    hits = capital_market_search(s)
    if not hits:
        return s  # fallback: pakota kutsu yrittämään, saadaan 404 jos väärä

    # Priorisoi täydellinen nimi- tai osuma
    s_upper = s.upper()
    best = None
    for h in hits:
        name = (h.get("instrumentName") or "").upper()
        if name == s_upper:
            best = h; break
        if s_upper in name and best is None:
            best = h
    if not best:
        best = hits[0]
    return best["epic"]

def capital_get_bid_ask(symbol_or_epic: str) -> Optional[Tuple[float, float]]:
    """
    Viimeisin bid/ask Capital RESTiltä (MINUTE, max=1).
    symbol_or_epic voi olla EPIC tai näyttönimi ("US SPX 500","EUR/USD"...).
    """
    sess, base = capital_rest_login()
    epic = _resolve_epic(symbol_or_epic)
    url = f"{base}/api/v1/prices/{epic}"
    params = {"resolution": "MINUTE", "max": 1}
    r = sess.get(url, params=params, timeout=15)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    data = r.json()

    bid = ask = None
    try:
        arr = data.get("prices") or data.get("data") or []
        if arr:
            last = arr[-1]
            # IG/Capital prices-objektissa on yleensä nämä:
            bid = last.get("bid")
            ask = last.get("ask")
            # Jos rakenteessa ei ole bid/ask, se voi olla candle-tyylinen -> None
    except Exception:
        pass

    if isinstance(bid, (int, float)) and isinstance(ask, (int, float)):
        return float(bid), float(ask)
    return None

def capital_get_candles(symbol_or_epic: str, tf: str, max_rows: int = 500) -> Optional[List[Dict[str, Any]]]:
    """
    OHLCV-kynttilät prices-endpointin kautta.
    tf: 15m -> MINUTE_15, 1h -> HOUR, 4h -> HOUR_4, 1d -> DAY
    """
    sess, base = capital_rest_login()
    epic = _resolve_epic(symbol_or_epic)
    res_map = {"15m": "MINUTE_15", "1h": "HOUR", "4h": "HOUR_4", "1d": "DAY"}
    res = res_map.get(tf.lower(), "HOUR")
    url = f"{base}/api/v1/prices/{epic}"
    params = {"resolution": res, "max": int(max_rows)}
    r = sess.get(url, params=params, timeout=20)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    data = r.json()
    return data.get("prices") or data.get("data") or []
