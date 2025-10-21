# -*- coding: utf-8 -*-
from __future__ import annotations
import os
import re
import time
import threading
from typing import Dict, Any, Optional, Tuple, List

try:
    import requests
except Exception:
    requests = None  # pragma: no cover

from tools.capital_session import capital_rest_login, capital_market_search

# Jaettu sessio ja base (capital_session itsekin cachettaa nämä, mutta pidetään viitteet täälläkin)
_SESS: Optional["requests.Session"] = None
_BASE: Optional[str] = None
_MANAGE_THREAD: Optional[threading.Thread] = None

def _norm_key(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", s.upper())

def _resolve_epic(symbol_or_name: str) -> str:
    s = (symbol_or_name or "").strip()
    if not s:
        return s
    # Env override – käytä vain jos arvo on oikea EPIC (pisteellinen tms. brokerin koodi)
    env = os.environ.get("CAPITAL_EPIC_" + _norm_key(s))
    if env and env.strip():
        return env.strip()
    # Jos näyttää jo EPICiltä (pisteitä, ei välilyöntejä), palauta
    if "." in s and " " not in s:
        return s
    # Markkinahaku
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
    # Fallback
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
    - epic: EPIC tai näyttönimi; resolvoidaan EPICiksi
    - direction: BUY/SELL
    - size: float
    """
    direction = (direction or "").upper()
    if direction not in ("BUY", "SELL"):
        raise ValueError(f"market_order: invalid direction '{direction}'")
    if size is None or size <= 0:
        raise ValueError(f"market_order: invalid size '{size}'")

    sess, base = capital_rest_login()
    # talteen myös globaaleihin (adoption/management voi hyödyntää)
    global _SESS, _BASE
    _SESS, _BASE = sess, base

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
            return {"ok": True, "data": d, "order_id": order_id, "position_id": pos_id}
        else:
            print(f"[ORDER][DEBUG] {tag} {url} -> {info}")
            last_err = f"{tag} {url} -> {info}"

    # Fallback: mock
    pos_id = f"local-{int(time.time()*1000)}"
    px = _last_price(sess, base, epic_res) or 0.0
    print(f"[ORDER][LOCAL] EPIC={epic_res} dir={direction} size={size} -> mock pos {pos_id} (last_err={last_err})")
    return {"ok": True, "data": {"local_only": True, "entry_px": px}, "position_id": pos_id}

# ------------ Adoption & hallinta (breakeven + trailing) ------------

def _fetch_open_positions(sess: "requests.Session", base: str) -> List[Dict[str, Any]]:
    """
    Yrittää hakea avoimet positiot geneerisesti /api/v1/positions päästä.
    Palauttaa listan dict-olioita joissa vähintään id, symbol(epic), side, size, entry_price, stop_loss.
    """
    url = f"{base}/api/v1/positions"
    try:
        r = sess.get(url, timeout=15)
        if r.status_code // 100 != 2:
            print(f"[POS][DEBUG] GET {url} -> {r.status_code} {r.text[:200]}")
            return []
        data = r.json()
        arr = data if isinstance(data, list) else data.get("positions", [])
        out = []
        for p in arr or []:
            out.append({
                "id": str(p.get("id") or p.get("position_id") or p.get("dealId") or p.get("uid") or ""),
                "symbol": p.get("symbol") or p.get("epic") or p.get("instrument") or "",
                "side": (p.get("side") or p.get("direction") or "").upper(),
                "size": float(p.get("size") or p.get("quantity") or p.get("units") or 0.0),
                "entry_price": float(p.get("entry_price") or p.get("openLevel") or p.get("avgPrice") or 0.0),
                "stop_loss": _maybe_float(p.get("stop_loss") or p.get("stopLevel")),
            })
        return [x for x in out if x["id"]]
    except Exception as e:
        print(f"[POS][ERROR] {e}")
        return []

def _set_stop_loss(sess: "requests.Session", base: str, position_id: str, new_sl: float) -> bool:
    try:
        url = f"{base}/api/v1/positions/{position_id}"
        body = {"stop_loss": float(new_sl)}
        r = sess.patch(url, json=body, timeout=10)
        if r.status_code // 100 == 2:
            print(f"[SL] pos={position_id} SL -> {new_sl}")
            return True
        print(f"[SL][DEBUG] PATCH {url} -> {r.status_code} {r.text[:200]}")
        return False
    except Exception as e:
        print(f"[SL][ERROR] {e}")
        return False

def _compute_R(side: str, entry: float, stop: Optional[float], px: float) -> Optional[float]:
    if stop is None:
        return None
    try:
        if side in ("BUY","LONG"):
            risk = entry - stop
            if risk <= 0:
                return None
            return (px - entry) / risk
        else:
            risk = stop - entry
            if risk <= 0:
                return None
            return (entry - px) / risk
    except Exception:
        return None

def adopt_open_positions() -> None:
    global _SESS, _BASE
    if _SESS is None or _BASE is None:
        try:
            _SESS, _BASE = capital_rest_login()
        except Exception as e:
            print(f"[ADOPT][ERROR] login: {e}")
            return
    pos = _fetch_open_positions(_SESS, _BASE)
    print(f"[ADOPT] Hallinnassa nyt {len(pos)} avoinna olevaa positioita (read-only).")

def _manage_once() -> None:
    global _SESS, _BASE
    if _SESS is None or _BASE is None:
        try:
            _SESS, _BASE = capital_rest_login()
        except Exception as e:
            print(f"[MANAGE][ERROR] login: {e}")
            return
    pos = _fetch_open_positions(_SESS, _BASE)
    if not pos:
        return
    breakeven_arm = _env_float("BREAKEVEN_ARM_R", 1.0) or 1.0
    trailing_enabled = (os.environ.get("TRAILING_ENABLED","0") == "1")
    trail_after = _env_float("TRAIL_AFTER_R", 1.5) or 1.5

    px_cache: Dict[str, float] = {}
    for p in pos:
        sym = p["symbol"]
        px = px_cache.get(sym)
        if px is None:
            px = _last_price(_SESS, _BASE, sym) or p["entry_price"]
            px_cache[sym] = px

        R = _compute_R(p["side"], p["entry_price"], p["stop_loss"], px)
        if R is None:
            continue

        # Breakeven
        if R >= breakeven_arm:
            new_sl = p["entry_price"]
            if p["stop_loss"] is None or \
               (p["side"] in ("BUY","LONG") and new_sl > p["stop_loss"]) or \
               (p["side"] in ("SELL","SHORT") and new_sl < p["stop_loss"]):
                _set_stop_loss(_SESS, _BASE, p["id"], new_sl)

        # Trailing (yksinkertainen 50% voitosta)
        if trailing_enabled and R >= trail_after:
            if p["side"] in ("BUY","LONG"):
                target_sl = p["entry_price"] + 0.5 * (px - p["entry_price"])
                if p["stop_loss"] is None or target_sl > p["stop_loss"]:
                    _set_stop_loss(_SESS, _BASE, p["id"], target_sl)
            else:
                target_sl = p["entry_price"] - 0.5 * (p["entry_price"] - px)
                if p["stop_loss"] is None or target_sl < p["stop_loss"]:
                    _set_stop_loss(_SESS, _BASE, p["id"], target_sl)

def manage_positions_loop(poll_sec: float = 10.0) -> None:
    print("[MANAGE] Loop start – breakeven/trailing käytössä."
          f" BE_R={_env_float('BREAKEVEN_ARM_R',1.0)} TRAIL_EN={os.environ.get('TRAILING_ENABLED','0')} TRAIL_R={_env_float('TRAIL_AFTER_R',1.5)}")
    while True:
        try:
            _manage_once()
        except Exception as e:
            print(f"[MANAGE][ERROR] {e}")
        time.sleep(poll_sec)

def connect_and_prepare() -> None:
    """
    Kutsutaan käynnistyksessä: adoptoi avoimet ja käynnistä hallintasilmukka env‑lippujen mukaan.
    - ADOPT_ON_START=1    -> adoptoi heti
    - MANAGE_OPEN_POSITIONS=1 -> käynnistä manage loop taustalle
    """
    adopt = os.environ.get("ADOPT_ON_START","0") == "1"
    manage = os.environ.get("MANAGE_OPEN_POSITIONS","0") == "1"
    # varmista sessio saataville
    global _SESS, _BASE, _MANAGE_THREAD
    try:
        _SESS, _BASE = capital_rest_login()
    except Exception as e:
        print(f"[CapitalClient][ERROR] Login epäonnistui: {e}")
        return
    if adopt:
        adopt_open_positions()
    if manage and (_MANAGE_THREAD is None or not _MANAGE_THREAD.is_alive()):
        t = threading.Thread(target=manage_positions_loop, name="cc-manage", daemon=True)
        t.start()
        _MANAGE_THREAD = t

def _maybe_float(x) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None

def _env_float(key: str, default: Optional[float] = None) -> Optional[float]:
    try:
        v = os.environ.get(key)
        return float(v) if v not in (None, "",) else default
    except Exception:
        return default
