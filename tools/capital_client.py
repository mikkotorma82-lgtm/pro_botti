# -*- coding: utf-8 -*-
"""
Capital client – tilauksen lähetys market_order-funktiolla capital_sessionin kautta.
- Ei vaadi CAPITAL_ACCOUNT_ID:tä, käytetään samoja kolmea env-arvoa kuin nyt: CAPITAL_API_BASE, CAPITAL_API_KEY, CAPITAL_USERNAME/PASSWORD
- EPIC resolvoidaan:
  1) CAPITAL_EPIC_<NORM> env (esim CAPITAL_EPIC_USSPX500=US500)
  2) capital_session.capital_market_search() -haku
  3) fallback: poistetaan '/' ja välilyönnit
- Lähetys:
  - POST /api/v1/positions/otc (IG/Capital-tyyli); jos 404/405, fallback POST /api/v1/positions
  - Lisää VERSION: 2 header
- Jos REST epäonnistuu → palauttaa local mock -position (ei kaada liveä)
"""

from __future__ import annotations
import os
import re
import time
from typing import Dict, Any, Optional

try:
    import requests
except Exception:
    requests = None  # pragma: no cover

from tools.capital_session import capital_rest_login, capital_market_search

def _norm_key(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", s.upper())

def _resolve_epic(symbol_or_name: str) -> str:
    s = (symbol_or_name or "").strip()
    if not s:
        return s
    # Env override
    env = os.environ.get("CAPITAL_EPIC_" + _norm_key(s))
    if env and env.strip():
        return env.strip()
    # Heuristiikka: jos näyttää jo EPIC:ltä (pisteitä, ei välilyöntejä), palauta
    if "." in s and " " not in s:
        return s
    # Haku
    try:
        hits = capital_market_search(s)
        if hits:
            target = s.upper().replace("/", "").replace(" ", "")
            for h in hits:
                sym = (h.get("symbol") or "").upper().replace("/", "").replace(" ", "")
                if sym and sym == target:
                    return h["epic"]
            # name exact -> contains -> first
            best = None
            for h in hits:
                name = (h.get("instrumentName") or "").upper()
                if name == s.upper():
                    best = h; break
                if (s.upper() in name) and best is None:
                    best = h
            return (best or hits[0])["epic"]
    except Exception:
        pass
    # Fallback: poista erotinmerkit
    return s.replace("/", "").replace(" ", "")

def _last_price(sess: "requests.Session", base: str, epic: str) -> Optional[float]:
    try:
        url = f"{base}/api/v1/prices/{epic}"
        r = sess.get(url, params={"resolution": "MINUTE", "max": 1}, timeout=10)
        if r.status_code // 100 != 2:
            return None
        data = r.json()
        arr = data.get("prices") or data.get("data") or []
        if not arr:
            return None
        d = arr[-1]
        for k1, k2 in (("bid","offer"), ("bid","ask"), ("sell","buy")):
            a, b = d.get(k1), d.get(k2)
            if isinstance(a, (int,float)) and isinstance(b, (int,float)):
                return (float(a) + float(b)) / 2.0
    except Exception:
        pass
    return None

def market_order(epic: str, direction: str, size: float) -> Dict[str, Any]:
    """
    Tee markkinatoimeksianto. Palauttaa dict: {ok, data, order_id?, position_id?} tai local mock.
    - epic: EPIC tai näyttönimi; resolvoidaan varmuuden vuoksi oikeaksi EPICiksi
    - direction: BUY/SELL
    - size: float
    """
    direction = (direction or "").upper()
    if direction not in ("BUY", "SELL"):
        raise ValueError(f"market_order: invalid direction '{direction}'")
    if size is None or size <= 0:
        raise ValueError(f"market_order: invalid size '{size}'")

    # Login (samat 3 env-arvoa), jaa sessio capital_sessionin kanssa
    sess, base = capital_rest_login()
    epic_res = _resolve_epic(epic)

    # Jotkin instanssit vaativat VERSION=2
    sess.headers.setdefault("VERSION", "2")

    # 1) IG/Capital-tyyli: positions/otc
    url_otc = f"{base}/api/v1/positions/otc"
    payload_otc = {
        "epic": epic_res,
        "direction": direction,
        "size": float(size),
        "orderType": "MARKET",
        "timeInForce": "FILL_OR_KILL",
        "forceOpen": True,
    }

    try:
        r = sess.post(url_otc, json=payload_otc, timeout=25)
        if r.status_code // 100 == 2:
            data = r.json() if r.text else {}
            return {
                "ok": True,
                "data": data,
                "order_id": str((data or {}).get("dealId") or (data or {}).get("order_id") or (data or {}).get("id") or ""),
                "position_id": str((data or {}).get("position") or (data or {}).get("position_id") or ""),
            }
        # 404/405 → fallback /positions
        if r.status_code in (404, 405):
            url_pos = f"{base}/api/v1/positions"
            payload_pos = {
                "symbol": epic_res,
                "side": direction,
                "size": float(size),
                "type": "MARKET",
                "tif": "FOK",
            }
            rr = sess.post(url_pos, json=payload_pos, timeout=25)
            rr.raise_for_status()
            data = rr.json() if rr.text else {}
            return {
                "ok": True,
                "data": data,
                "order_id": str((data or {}).get("order_id") or (data or {}).get("id") or ""),
                "position_id": str((data or {}).get("position") or (data or {}).get("position_id") or ""),
            }
        # jokin muu HTTP-virhe → nosta
        r.raise_for_status()
    except Exception as e:
        print(f"[ERROR] REST order epäonnistui: {e}")

    # 2) Fallback: local mock, jotta live voi jatkaa
    pos_id = f"local-{int(time.time()*1000)}"
    px = _last_price(sess, base, epic_res) or 0.0  # best effort
    print(f"[ORDER][LOCAL] {epic_res} {direction} {size} type=MARKET -> mock pos {pos_id}")
    return {"ok": True, "data": {"local_only": True, "entry_px": px}, "position_id": pos_id}
