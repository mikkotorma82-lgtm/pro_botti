#!/usr/bin/env python3
from __future__ import annotations
import os
import time
import json
import pickle
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List
import urllib.parse

import requests

# Env
# CAPITAL_API_BASE=https://api-capital.backend-capital.com
# CAPITAL_API_KEY=...
# CAPITAL_USERNAME=...
# CAPITAL_PASSWORD=...
# (optional) CAPITAL_ACCOUNT_TYPE=CFD
# (optional) CAPITAL_LOGIN_TTL=540
# (optional) CAPITAL_RATE_LIMIT_SLEEP=65

STATE_DIR = Path(__file__).resolve().parents[1] / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
SESSION_PATH = STATE_DIR / "capital_session.json"
COOKIES_PATH = STATE_DIR / "capital_cookies.pkl"

_CAPITAL_SESS: Optional[requests.Session] = None
_CAPITAL_BASE: Optional[str] = None
_CAPITAL_LAST_LOGIN_TS: float = 0.0
_CAPITAL_LOGIN_TTL: int = int(os.getenv("CAPITAL_LOGIN_TTL", "540"))
_RATE_LIMIT_SLEEP: int = int(os.getenv("CAPITAL_RATE_LIMIT_SLEEP", "65"))
_COOLDOWN_UNTIL: float = 0.0  # globaali WAF-cooldown

def _mandatory_env(key: str) -> str:
    v = os.getenv(key, "").strip()
    if not v:
        raise RuntimeError(f"Missing {key} env")
    return v

def _is_probably_epic(s: str) -> bool:
    return ("." in s) and (" " not in s)

def _env_epic_for(symbol: str) -> Optional[str]:
    key = "CAPITAL_EPIC_" + "".join(ch for ch in symbol.upper() if ch.isalnum())
    return os.getenv(key)

def _load_cookies(sess: requests.Session) -> None:
    try:
        if COOKIES_PATH.exists():
            with COOKIES_PATH.open("rb") as f:
                jar = pickle.load(f)
            sess.cookies.update(jar)
    except Exception:
        pass

def _save_cookies(sess: requests.Session) -> None:
    try:
        with COOKIES_PATH.open("wb") as f:
            pickle.dump(sess.cookies, f)
    except Exception:
        pass

def _load_cached_session() -> Optional[Tuple[str, str, float]]:
    try:
        if SESSION_PATH.exists():
            obj = json.loads(SESSION_PATH.read_text())
            cst = obj.get("cst"); sec = obj.get("sec"); ts = float(obj.get("login_time", 0))
            if cst and sec and ts > 0:
                return cst, sec, ts
    except Exception:
        pass
    return None

def _save_cached_session(cst: str, sec: str, login_time: float) -> None:
    try:
        SESSION_PATH.write_text(json.dumps({"cst": cst, "sec": sec, "login_time": login_time}))
    except Exception:
        pass

def capital_rest_login(force: bool = False) -> Tuple[requests.Session, str]:
    global _CAPITAL_SESS, _CAPITAL_BASE, _CAPITAL_LAST_LOGIN_TS, _COOLDOWN_UNTIL

    now = time.time()
    if now < _COOLDOWN_UNTIL:
        wait = int(_COOLDOWN_UNTIL - now)
        raise RuntimeError(f"Capital login cooling down due to prior 429. Try again in ~{wait}s")

    base = _mandatory_env("CAPITAL_API_BASE").rstrip("/")
    api_key = _mandatory_env("CAPITAL_API_KEY")
    username = _mandatory_env("CAPITAL_USERNAME")
    password = _mandatory_env("CAPITAL_PASSWORD")
    account_type = os.getenv("CAPITAL_ACCOUNT_TYPE", "CFD")

    # Reuse in-memory session if valid
    if (not force) and _CAPITAL_SESS is not None and (now - _CAPITAL_LAST_LOGIN_TS < _CAPITAL_LOGIN_TTL):
        return _CAPITAL_SESS, _CAPITAL_BASE  # type: ignore[return-value]

    # Create session and load cookies
    s = requests.Session()
    s.headers.update({
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-CAP-API-KEY": api_key,
        "User-Agent": "pro-botti/1.0 (+https://github.com/mikkotorma82-lgtm/pro_botti)"
    })
    _load_cookies(s)

    # Try to reuse cached tokens if still valid
    cached = _load_cached_session()
    if cached and not force:
        cst, sec, ts = cached
        age = now - ts
        if age < _CAPITAL_LOGIN_TTL:
            s.headers.update({"CST": cst, "X-SECURITY-TOKEN": sec})
            _CAPITAL_SESS, _CAPITAL_BASE, _CAPITAL_LAST_LOGIN_TS = s, base, ts
            return _CAPITAL_SESS, _CAPITAL_BASE

    url = f"{base}/api/v1/session"
    payload: Dict[str, Any] = {"identifier": username, "password": password}

    backoffs = [_RATE_LIMIT_SLEEP, max(_RATE_LIMIT_SLEEP, 90), max(_RATE_LIMIT_SLEEP, 120)]
    last_err = None
    for attempt, pause in enumerate(backoffs, start=1):
        r = s.post(url, json=payload, timeout=25)
        if r.status_code == 429:
            # Set global cooldown and sleep once, then retry
            _COOLDOWN_UNTIL = time.time() + pause
            time.sleep(pause)
            last_err = {"status": r.status_code, "text": r.text[:200]}
            continue

        if r.status_code in (200, 201):
            cst = r.headers.get("CST")
            xsec = r.headers.get("X-SECURITY-TOKEN")
            if not cst or not xsec:
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
            _save_cookies(s)
            _save_cached_session(cst, xsec, time.time())

            _CAPITAL_SESS, _CAPITAL_BASE, _CAPITAL_LAST_LOGIN_TS = s, base, time.time()
            return _CAPITAL_SESS, _CAPITAL_BASE

        if r.status_code in (401, 403):
            try: err = r.json()
            except Exception: err = {"body": r.text}
            raise RuntimeError(f"Capital login failed ({r.status_code}). Response: {err}")

        last_err = {"status": r.status_code, "text": r.text[:200]}
        r.raise_for_status()

    # If all attempts failed with 429, extend cooldown and fail clearly
    if last_err and last_err.get("status") == 429:
        _COOLDOWN_UNTIL = time.time() + max(backoffs)
        raise RuntimeError(f"Capital login: rate-limited (429). Cooldown active for ~{max(backoffs)}s.")
    raise RuntimeError(f"Capital login: unexpected errors. last={last_err}")

def capital_market_search(query: str, limit: int = 25) -> List[Dict[str, Any]]:
    sess, base = capital_rest_login()
    q = urllib.parse.quote(query)
    paths = [f"/api/v1/markets?searchTerm={q}", f"/markets?searchTerm={q}"]
    out: List[Dict[str, Any]] = []
    for p in paths:
        url = f"{base}{p}"
        r = sess.get(url, timeout=20)
        if r.status_code // 100 != 2:
            continue
        data = r.json()
        items = data.get("markets") or data.get("data") or []
        for it in items:
            epic = it.get("epic") or it.get("EPIC") or it.get("id")
            name = it.get("instrumentName") or it.get("name") or it.get("symbol")
            if epic:
                out.append({"epic": epic, "instrumentName": name, "raw": it})
        if out:
            break
    return out[:limit]

def _resolve_epic(symbol_or_name: str) -> str:
    s = symbol_or_name.strip()
    if _is_probably_epic(s):
        return s
    env_epic = _env_epic_for(s)
    if env_epic:
        return env_epic.strip()
    hits = capital_market_search(s)
    if not hits:
        return s
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
            bid = last.get("bid")
            ask = last.get("ask")
    except Exception:
        pass
    if isinstance(bid, (int, float)) and isinstance(ask, (int, float)):
        return float(bid), float(ask)
    return None

def capital_get_candles(symbol_or_epic: str, tf: str, max_rows: int = 500) -> Optional[List[Dict[str, Any]]]:
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
