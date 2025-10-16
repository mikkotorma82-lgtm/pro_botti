# -*- coding: utf-8 -*-
from __future__ import annotations
import os
import re
import time
from typing import Dict, Any, Optional, Tuple, List

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
    env = os.environ.get("CAPITAL_EPIC_" + _norm_key(s))
    if env and env.strip():
        return env.strip()
    if "." in s and " " not in s:
        return s
    try:
        hits = capital_market_search(s)
        if hits:
            target = s.upper().replace("/", "").replace(" ", "")
            for h in hits:
                sym = (h.get("symbol") or "").upper().replace("/", "").replace(" ", "")
                if sym and sym == target:
                    return h["epic"]
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

def _try_post(sess: "requests.Session", url: str, payload: Dict[str, Any]) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    try:
        r = sess.post(url, json=payload, timeout=25)
        ok = (r.status_code // 100 == 2)
        body = r.text[:500] if r.text else ""
        if ok:
            return True, (r.json() if r.text else {}), f"{r.status_code}"
        else:
            return False, None, f"{r.status_code} {body}"
    except Exception as e:
        return False, None, f"EXC {e}"

def _confirm_deal(sess: "requests.Session", base: str, deal_ref: str, tries: int = 3, sleep_s: float = 0.8) -> Dict[str, Any]:
    """
    IG/Capital confirm: palauttaa mm. dealId, status, reason, level jne.
    """
    url = f"{base}/api/v1/confirms/{deal_ref}"
    last = {}
    for i in range(tries):
        try:
            r = sess.get(url, timeout=10)
            if r.status_code // 100 == 2 and r.text:
                data = r.json()
                if data.get("dealId") or data.get("dealStatus") or data.get("reason"):
                    return data
                last = data
            else:
                last = {"status": r.status_code, "body": r.text[:200]}
        except Exception as e:
            last = {"error": str(e)}
        time.sleep(sleep_s)
    return last or {}

def market_order(epic: str, direction: str, size: float) -> Dict[str, Any]:
    """
    Tee markkinatoimeksianto. Palauttaa dict: {ok, data, order_id?, position_id?} tai local mock.
    """
    direction = (direction or "").upper()
    if direction not in ("BUY", "SELL"):
        raise ValueError(f"market_order: invalid direction '{direction}'")
    if size is None or size <= 0:
        raise ValueError(f"market_order: invalid size '{size}'")

    sess, base = capital_rest_login()
    sess.headers.setdefault("Accept", "application/json")
    sess.headers.setdefault("Content-Type", "application/json")
    sess.headers.setdefault("VERSION", "2")

    epic_res = _resolve_epic(epic)
    print(f"[ORDER][DEBUG] resolved EPIC={epic_res}")

    attempts: List[Tuple[str, Dict[str, Any], str]] = [
        # 1) positions (symbol/side/type)
        (f"{base}/api/v1/positions", {
            "symbol": epic_res,
            "side": direction,
            "size": float(size),
            "type": "MARKET",
        }, "positions(symbol/side/type)"),
        # 2) positions (epic/direction/orderType)
        (f"{base}/api/v1/positions", {
            "epic": epic_res,
            "direction": direction,
            "size": float(size),
            "orderType": "MARKET",
        }, "positions(epic/direction/orderType)"),
        # 3) positions/otc (IG/Capital)
        (f"{base}/api/v1/positions/otc", {
            "epic": epic_res,
            "direction": direction,
            "size": float(size),
            "orderType": "MARKET",
            "timeInForce": "FILL_OR_KILL",
            "forceOpen": True,
        }, "positions/otc"),
        # 4) deal (fallback)
        (f"{base}/api/v1/deal", {
            "epic": epic_res,
            "direction": direction,
            "size": float(size),
            "orderType": "MARKET",
        }, "deal"),
    ]

    last_err = ""
    for url, payload, tag in attempts:
        ok, data, info = _try_post(sess, url, payload)
        if ok:
            d = data or {}
            print(f"[ORDER][REST] EPIC={epic_res} dir={direction} size={size} via {url}")
            # Jos vastauksessa on dealReference, yritä confirm
            deal_ref = d.get("dealReference") or d.get("deal_ref") or d.get("reference")
            order_id = str(d.get("dealId") or d.get("order_id") or d.get("id") or "")
            pos_id = str(d.get("position") or d.get("position_id") or "")

            if deal_ref and not order_id:
                conf = _confirm_deal(sess, base, deal_ref)
                if conf:
                    order_id = str(conf.get("dealId") or order_id or "")
                    # IG-tyypissä position-id ei aina tule suoraan confirmista; jätetään tyhjäksi jos ei ole

            return {
                "ok": True,
                "data": d,
                "order_id": order_id,
                "position_id": pos_id,
            }
        else:
            print(f"[ORDER][DEBUG] {tag} {url} -> {info}")
            last_err = f"{tag} {url} -> {info}"

    # Fallback: mock
    pos_id = f"local-{int(time.time()*1000)}"
    px = _last_price(sess, base, epic_res) or 0.0
    print(f"[ORDER][LOCAL] EPIC={epic_res} dir={direction} size={size} -> mock pos {pos_id} (last_err={last_err})")
    return {"ok": True, "data": {"local_only": True, "entry_px": px}, "position_id": pos_id}
