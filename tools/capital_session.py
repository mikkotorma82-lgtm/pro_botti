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
import pandas as pd

# ENV (LIVE):
#   CAPITAL_API_BASE=https://api-capital.backend-capital.com
#   CAPITAL_API_KEY=...
#   CAPITAL_USERNAME=...
#   CAPITAL_PASSWORD=...   # API key password
# Optional:
#   CAPITAL_ACCOUNT_TYPE=CFD
#   CAPITAL_LOGIN_TTL=540             # re-login interval seconds (default 9 min; token ~10 min)
#   CAPITAL_RATE_LIMIT_SLEEP=90       # base sleep on 429 (seconds)
#   CAPITAL_RESOLVE_CACHE_TTL=2592000 # EPIC cache TTL seconds (default 30 days)

ROOT_DIR = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT_DIR / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)

SESSION_PATH = STATE_DIR / "capital_session.json"
COOKIES_PATH = STATE_DIR / "capital_cookies.pkl"
EPIC_CACHE_PATH = STATE_DIR / "capital_epic_map.json"

_CAPITAL_SESS: Optional[requests.Session] = None
_CAPITAL_BASE: Optional[str] = None
_CAPITAL_LAST_LOGIN_TS: float = 0.0

_LOGIN_TTL: int = int(os.getenv("CAPITAL_LOGIN_TTL", "540"))
_RATE_LIMIT_SLEEP: int = int(os.getenv("CAPITAL_RATE_LIMIT_SLEEP", "90"))
_RESOLVE_CACHE_TTL: int = int(os.getenv("CAPITAL_RESOLVE_CACHE_TTL", str(30 * 24 * 3600)))

_COOLDOWN_UNTIL: float = 0.0  # global cooldown end time after 429


def _mandatory_env(key: str) -> str:
    v = os.getenv(key, "").strip()
    if not v:
        raise RuntimeError(f"Missing {key} env")
    return v


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception:
        pass
    return default


def _save_json(path: Path, obj: Any) -> None:
    try:
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2))
    except Exception:
        pass


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


def _load_session_cache() -> Optional[Tuple[str, str, float]]:
    obj = _load_json(SESSION_PATH, {})
    cst = obj.get("cst")
    sec = obj.get("sec")
    ts = float(obj.get("login_time", 0) or 0)
    if cst and sec and ts > 0:
        return cst, sec, ts
    return None


def _save_session_cache(cst: str, sec: str, ts: float) -> None:
    _save_json(SESSION_PATH, {"cst": cst, "sec": sec, "login_time": ts})


def capital_rest_login(force: bool = False) -> Tuple[requests.Session, str]:
    """
    Log in to Capital LIVE REST once and reuse tokens/cookies across process and runs.
    - No TOTP. If backend enforces TOTP, raise descriptive error.
    - Aggressive protection against 429 with cooldown.
    """
    global _CAPITAL_SESS, _CAPITAL_BASE, _CAPITAL_LAST_LOGIN_TS, _COOLDOWN_UNTIL

    now = time.time()
    if now < _COOLDOWN_UNTIL:
        wait = int(_COOLDOWN_UNTIL - now) + 1
        raise RuntimeError(f"Capital login cooling down due to prior 429. Try again in ~{wait}s")

    base = _mandatory_env("CAPITAL_API_BASE").rstrip("/")
    api_key = _mandatory_env("CAPITAL_API_KEY")
    username = _mandatory_env("CAPITAL_USERNAME")
    password = _mandatory_env("CAPITAL_PASSWORD")
    account_type = os.getenv("CAPITAL_ACCOUNT_TYPE", "CFD")

    # Reuse in-memory session if still fresh
    if (not force) and _CAPITAL_SESS is not None and (now - _CAPITAL_LAST_LOGIN_TS < _LOGIN_TTL):
        return _CAPITAL_SESS, _CAPITAL_BASE  # type: ignore[return-value]

    # New session; load cookies
    s = requests.Session()
    s.headers.update({
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-CAP-API-KEY": api_key,
        "User-Agent": "pro-botti/1.0 (+https://github.com/mikkotorma82-lgtm/pro_botti)"
    })
    _load_cookies(s)

    # Try cached tokens first (persisted)
    cached = _load_session_cache()
    if cached and not force:
        cst, sec, ts = cached
        age = now - ts
        if age < _LOGIN_TTL:
            s.headers.update({"CST": cst, "X-SECURITY-TOKEN": sec})
            if account_type:
                s.headers.setdefault("X-CAP-ACCOUNT-TYPE", account_type)
            _CAPITAL_SESS, _CAPITAL_BASE, _CAPITAL_LAST_LOGIN_TS = s, base, ts
            return _CAPITAL_SESS, _CAPITAL_BASE

    # Perform login
    url = f"{base}/api/v1/session"
    payload: Dict[str, Any] = {"identifier": username, "password": password}

    # Backoffs: increasing sleeps on repeated 429
    backoffs = [_RATE_LIMIT_SLEEP, max(_RATE_LIMIT_SLEEP, 120), max(_RATE_LIMIT_SLEEP, 180)]
    last_err = None
    for attempt, pause in enumerate(backoffs, start=1):
        r = s.post(url, json=payload, timeout=25)
        if r.status_code == 429:
            # Set cooldown and pause, then retry
            _COOLDOWN_UNTIL = time.time() + pause
            time.sleep(pause)
            last_err = {"status": r.status_code, "text": r.text[:200]}
            continue

        if r.status_code in (200, 201):
            cst = r.headers.get("CST")
            xsec = r.headers.get("X-SECURITY-TOKEN")
            if not cst or not xsec:
                # Some tenants put tokens in body (rare)
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
            _save_session_cache(cst, xsec, time.time())

            _CAPITAL_SESS, _CAPITAL_BASE, _CAPITAL_LAST_LOGIN_TS = s, base, time.time()
            return _CAPITAL_SESS, _CAPITAL_BASE

        if r.status_code in (401, 403):
            try:
                err = r.json()
            except Exception:
                err = {"body": r.text}
            raise RuntimeError(f"Capital login failed ({r.status_code}). Server may enforce TOTP. Response: {err}")

        last_err = {"status": r.status_code, "text": r.text[:200]}
        r.raise_for_status()

    # If all attempts resulted in 429, extend cooldown and abort
    if last_err and last_err.get("status") == 429:
        _COOLDOWN_UNTIL = time.time() + max(backoffs)
        raise RuntimeError(f"Capital login: rate-limited (429). Cooldown active for ~{max(backoffs)}s.")
    raise RuntimeError(f"Capital login: unexpected errors. last={last_err}")


def _epic_cache_load() -> Dict[str, Dict[str, Any]]:
    obj = _load_json(EPIC_CACHE_PATH, {})
    if not isinstance(obj, dict):
        return {}
    return obj


def _epic_cache_save(cache: Dict[str, Dict[str, Any]]) -> None:
    _save_json(EPIC_CACHE_PATH, cache)


def _env_epic_for(symbol: str) -> Optional[str]:
    # CAPITAL_EPIC_<UPPERALNUM>
    key = "CAPITAL_EPIC_" + "".join(ch for ch in symbol.upper() if ch.isalnum())
    v = os.getenv(key, "").strip()
    return v or None


def _is_prob_epic(s: str) -> bool:
    # EPIC typically has dots and no spaces: e.g., IX.D.SPTRD.D
    return ("." in s) and (" " not in s)


def capital_market_search(query: str, limit: int = 25) -> List[Dict[str, Any]]:
    """
    Search markets by display name; returns entries with epic, instrumentName, symbol.
    """
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
            symbol = it.get("symbol") or ""
            if epic:
                out.append({"epic": epic, "instrumentName": name, "symbol": symbol, "raw": it})
        if out:
            break
    return out[:limit]


def _resolve_epic(symbol_or_name: str) -> str:
    """
    Resolve display name or EPIC -> EPIC with caching.
    Priority:
      1) Already EPIC-like -> return as-is
      2) Env override CAPITAL_EPIC_<KEY>
      3) Cache hit (capital_epic_map.json) and not expired
      4) Prefer symbol exact match (normalized: remove '/', spaces) over name match
      5) Name exact, then name contains, else first
    """
    s = symbol_or_name.strip()
    if _is_prob_epic(s):
        return s

    env_epic = _env_epic_for(s)
    if env_epic:
        return env_epic

    cache = _epic_cache_load()
    key = s.upper()
    now = time.time()
    hit = cache.get(key)
    if hit and (now - float(hit.get("ts", 0))) < _RESOLVE_CACHE_TTL:
        return hit["epic"]

    hits = capital_market_search(s)
    if not hits:
        cache[key] = {"epic": s, "name": s, "ts": now}
        _epic_cache_save(cache)
        return s

    s_upper = s.upper()
    sym_target = s_upper.replace("/", "").replace(" ", "")

    # 4) symbol exact match (normalized)
    for h in hits:
        sym = (h.get("symbol") or "").upper().replace("/", "").replace(" ", "")
        if sym and sym == sym_target:
            epic = h["epic"]
            cache[key] = {"epic": epic, "name": h.get("instrumentName"), "ts": now}
            _epic_cache_save(cache)
            return epic

    # 5) name exact -> name contains -> first
    best = None
    for h in hits:
        name = (h.get("instrumentName") or "").upper()
        if name == s_upper:
            best = h
            break
        if (s_upper in name) and best is None:
            best = h
    if not best:
        best = hits[0]

    epic = best["epic"]
    cache[key] = {"epic": epic, "name": best.get("instrumentName"), "ts": now}
    _epic_cache_save(cache)
    return epic


def _extract_bid_ask_from_price_entry(entry: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    """
    Try multiple shapes of price entries:
      - direct: {'bid': ..., 'offer': ...} or {'bid': ..., 'ask': ...}
      - nested: {'closePrice': {'bid': ..., 'ask': ...}} etc.
      - sell/buy synonyms
    """
    def pick(d: Dict[str, Any]) -> Optional[Tuple[float, float]]:
        if not isinstance(d, dict):
            return None
        if "bid" in d and "offer" in d and isinstance(d["bid"], (int, float)) and isinstance(d["offer"], (int, float)):
            return float(d["bid"]), float(d["offer"])
        if "bid" in d and "ask" in d and isinstance(d["bid"], (int, float)) and isinstance(d["ask"], (int, float)):
            return float(d["bid"]), float(d["ask"])
        if "sell" in d and "buy" in d and isinstance(d["sell"], (int, float)) and isinstance(d["buy"], (int, float)):
            return float(d["sell"]), float(d["buy"])
        return None

    # direct on entry
    got = pick(entry)
    if got:
        return got

    # nested typical IG shapes
    for k in ("closePrice", "openPrice", "lastTradedPrice", "highPrice", "lowPrice", "midPrice", "price"):
        sub = entry.get(k)
        got = pick(sub) if isinstance(sub, dict) else None
        if got:
            return got
    return None


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

    arr = data.get("prices") or data.get("data") or []
    if not arr:
        return None

    last = arr[-1]
    pair = _extract_bid_ask_from_price_entry(last)
    return pair


def _res_map(tf: str) -> str:
    m = {"1m": "MINUTE", "5m": "MINUTE_5", "15m":"MINUTE_15", "30m":"MINUTE_30",
         "1h":"HOUR", "4h":"HOUR_4", "1d":"DAY"}
    return m.get(tf.lower(), "HOUR")


def capital_get_candles(symbol_or_epic: str, tf: str, max_rows: int = 500) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch OHLCV 'prices' list via prices endpoint (single page).
    """
    sess, base = capital_rest_login()
    epic = _resolve_epic(symbol_or_epic)
    url = f"{base}/api/v1/prices/{epic}"
    params = {"resolution": _res_map(tf), "max": int(max_rows)}
    r = sess.get(url, params=params, timeout=20)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    data = r.json()
    return data.get("prices") or data.get("data") or []


def capital_get_candles_paged(symbol_or_epic: str, tf: str, total_limit: int = 2000, page_size: int = 200,
                              sleep_sec: float = 0.8) -> List[Dict[str, Any]]:
    """
    Paged fetch via prices endpoint using pageNumber. Many tenants support:
      GET /api/v1/prices/{EPIC}?resolution=HOUR&max=200&pageNumber=1
    Fallback: if pageNumber not supported (no change in data), returns just the first page.
    """
    sess, base = capital_rest_login()
    epic = _resolve_epic(symbol_or_epic)
    url = f"{base}/api/v1/prices/{epic}"
    res = _res_map(tf)

    results: List[Dict[str, Any]] = []
    page = 1
    last_first_ts = None
    grabbed = 0

    while grabbed < total_limit:
        params = {"resolution": res, "max": int(page_size), "pageNumber": int(page)}
        r = sess.get(url, params=params, timeout=25)
        if r.status_code == 404:
            break
        if r.status_code == 429:
            time.sleep(max(_RATE_LIMIT_SLEEP, 90))
            continue
        r.raise_for_status()
        data = r.json()
        items = data.get("prices") or data.get("data") or []
        if not items:
            break

        # Detect if paging not supported (same chunk repeats)
        first_ts = (items[0].get("snapshotTimeUTC") or items[0].get("snapshotTime") or items[0].get("updateTimeUTC"))
        if page == 2 and last_first_ts and first_ts == last_first_ts:
            # paging likely unsupported; keep only first page
            break

        results.extend(items)
        grabbed += len(items)
        last_first_ts = first_ts
        page += 1
        time.sleep(sleep_sec)

        # Stop if last page smaller than page_size
        if len(items) < page_size:
            break

    # Ensure newest-last order
    return results


def _entry_to_ohlc(entry: Dict[str, Any]) -> Dict[str, Any]:
    # time
    t = entry.get("snapshotTimeUTC") or entry.get("snapshotTime") or entry.get("updateTimeUTC")
    # O/H/L/C as mid (prefer midPrice, else avg(bid,ask) from close/open/high/low)
    def mid_from(d: Optional[Dict[str, Any]]) -> Optional[float]:
        if not isinstance(d, dict):
            return None
        if "mid" in d and isinstance(d["mid"], (int, float)):
            return float(d["mid"])
        bid = d.get("bid"); ask = d.get("ask") if "ask" in d else d.get("offer")
        if isinstance(bid, (int, float)) and isinstance(ask, (int, float)):
            return (float(bid) + float(ask)) / 2.0
        # sell/buy synonym
        sell = d.get("sell"); buy = d.get("buy")
        if isinstance(sell, (int, float)) and isinstance(buy, (int, float)):
            return (float(sell) + float(buy)) / 2.0
        return None

    o = mid_from(entry.get("openPrice"))
    h = mid_from(entry.get("highPrice"))
    l = mid_from(entry.get("lowPrice"))
    c = mid_from(entry.get("closePrice"))

    vol = entry.get("lastTradedVolume")
    if not isinstance(vol, (int, float)):
        vol = 0.0

    return {"time": t, "open": o, "high": h, "low": l, "close": c, "volume": float(vol)}


def capital_get_candles_df(symbol_or_epic: str, tf: str, total_limit: int = 2000,
                           page_size: int = 200, sleep_sec: float = 0.8) -> pd.DataFrame:
    """
    Return standardized DataFrame [time, open, high, low, close, volume] UTC.
    Uses paged fetch to accumulate up to total_limit bars (newest last).
    """
    items = capital_get_candles_paged(symbol_or_epic, tf, total_limit=total_limit, page_size=page_size, sleep_sec=sleep_sec)
    if not items:
        return pd.DataFrame(columns=["time","open","high","low","close","volume"])
    rows = [_entry_to_ohlc(x) for x in items]
    df = pd.DataFrame(rows)
    # coerce time
    if "time" in df.columns:
        try:
            df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
        except Exception:
            pass
    df = df.dropna(subset=["time"])
    # drop rows if O/H/L/C missing – keep safe; or fill forward?
    for k in ("open","high","low","close","volume"):
        if k not in df.columns:
            df[k] = None
    df = df[["time","open","high","low","close","volume"]]
    df = df.sort_values("time").reset_index(drop=True)
    return df
