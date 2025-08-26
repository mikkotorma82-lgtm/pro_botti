from __future__ import annotations
import os, json, time
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Tuple
from tools._dotenv import load_dotenv

load_dotenv()
from tools.util_http import req

BASE = (
    os.getenv("CAPITAL_API_BASE")
    or os.getenv("CAPITAL_BASE_URL")
    or "https://demo-api-capital.backend-capital.com"
).rstrip("/")
API = BASE + "/api/v1"

ECACHE = Path("data/epic_cache.json")
RCACHE = Path("data/rules_cache.json")
ECACHE.parent.mkdir(parents=True, exist_ok=True)
_epic = json.loads(ECACHE.read_text()) if ECACHE.exists() else {}
_rules = json.loads(RCACHE.read_text()) if RCACHE.exists() else {}


def _save():
    ECACHE.write_text(json.dumps(_epic, indent=2, ensure_ascii=False))
    RCACHE.write_text(json.dumps(_rules, indent=2, ensure_ascii=False))


def _headers(tok: dict | None = None):
    h = {
        "X-CAP-API-KEY": os.getenv("CAPITAL_API_KEY") or os.getenv("CAPITAL_KEY", ""),
        "Accept": "application/json",
    }
    if tok:
        h.update(
            {
                "CST": tok.get("CST", ""),
                "X-SECURITY-TOKEN": tok.get("X-SECURITY-TOKEN", ""),
            }
        )
    return h


def login() -> dict:
    r = req(
        "POST",
        API + "/session",
        headers=_headers(),
        json={
            "identifier": os.getenv("CAPITAL_USERNAME")
            or os.getenv("CAPITAL_IDENTIFIER"),
            "password": os.getenv("CAPITAL_PASSWORD"),
            "encryptedPassword": False,
        },
    )
    return {
        "CST": r.headers.get("CST", ""),
        "X-SECURITY-TOKEN": r.headers.get("X-SECURITY-TOKEN", ""),
    }


# --- EPIC RESOLUTION ---

ALIAS = {
    "US500": ["US 500", "S&P 500", "SPTRD", "SPX", "S&P500"],
    "US100": ["US 100", "NASDAQ 100", "NAS100", "NDX"],
    "US30": ["US 30", "Wall Street", "Dow Jones", "DJI", "DOW"],
    "GER40": ["Germany 40", "DAX", "DE40"],
    "FRA40": ["France 40", "CAC40", "CAC 40"],
    "UK100": ["FTSE 100", "FTSE"],
    "EU50": ["EU 50", "Euro Stoxx 50", "SX5E"],
    "JPN225": ["Japan 225", "Nikkei 225", "NKY"],
    "HK50": ["Hong Kong 50", "HSI"],
    "AUS200": ["Australia 200", "ASX 200", "AS51"],
}


def _wanted_types(sym: str) -> tuple[set[str], set[str]]:
    s = sym.upper()
    if len(s) == 6 and s.isalpha():  # FX pairs
        return {"CURRENCIES", "FX"}, {"CURRENCIES", "FX"}
    if any(
        k in s
        for k in (
            "US500",
            "US100",
            "US30",
            "GER40",
            "FRA40",
            "UK100",
            "ESP35",
            "IT40",
            "EU50",
            "JPN225",
            "HK50",
            "AUS200",
        )
    ):
        return {"INDICES", "INDEX"}, {"INDICES", "INDEX"}
    if s in {"XAUUSD", "XAGUSD", "WTI", "BRENT", "NATGAS"}:
        return {"COMMODITIES", "COMMODITY"}, {"COMMODITIES", "COMMODITY"}
    return {"SHARES", "EQUITIES"}, {"SHARES", "EQUITIES"}


def _rank(hit: dict, s: str, itypes: set[str], mtypes: set[str]) -> int:
    score = 0
    ep = (hit.get("epic") or "").upper()
    it = (hit.get("instrumentType") or "").upper()
    mt = (hit.get("marketType") or "").upper()
    name = (hit.get("instrumentName") or "").upper().replace(" ", "")
    sym = (hit.get("symbol") or "").upper().replace(" ", "")
    status = (hit.get("marketStatus") or "").upper()
    # type match
    if it in itypes:
        score += 5
    if mt in mtypes:
        score += 3
    # exact-ish matches
    if s == sym or s == name:
        score += 6
    if s in (sym, name):
        score += 2
    # prefer cash/CFD spot epics
    if ep.endswith(".IP"):
        score += 3
    if ".CFD." in ep or ".SPOT." in ep or ".CASH." in ep:
        score += 3
    # penalize dated/futures codes (month+year)
    if any(ch.isdigit() for ch in ep[-4:]):
        score -= 4
    if status == "TRADEABLE":
        score += 1
    # special boosts
    if len(s) == 6 and s.isalpha() and ep.startswith("CS."):
        score += 4  # FX cash
    if s in {"US500", "US100", "US30"} and ep.startswith("IX."):
        score += 4
    return score


def resolve_epic(symbol: str, tok: dict) -> tuple[str, dict]:
    s = symbol.upper()
    if s in _epic:
        return _epic[s]["epic"], _epic[s]["hit"]
    itypes, mtypes = _wanted_types(s)
    terms = [s] + ALIAS.get(s, [])
    candidates = []
    for term in terms:
        r = req(
            "GET", API + "/markets", headers=_headers(tok), params={"searchTerm": term}
        )
        items = r.json().get("markets", []) or []
        candidates.extend(items)
    if not candidates:
        raise RuntimeError(f"EPIC not found for {s}")
    ranked = sorted(candidates, key=lambda x: _rank(x, s, itypes, mtypes), reverse=True)
    hit = ranked[0]
    _epic[s] = {"epic": hit["epic"], "hit": hit}
    _save()
    return hit["epic"], hit


def market_rules(epic: str, tok: dict) -> dict:
    if epic in _rules:
        return _rules[epic]
    md = req("GET", API + f"/markets/{epic}", headers=_headers(tok)).json()
    dr = md.get("dealingRules") or {}
    snap = md.get("snapshot") or {}
    rules = {
        "min_size": float((dr.get("minDealSize") or {}).get("value", 0) or 0),
        "step": float((dr.get("minDealSizeFractional") or {}).get("value", 0) or 1.0),
        "lot_size": float((md.get("instrument") or {}).get("lotSize", 1) or 1),
        "currency": snap.get("currency") or "EUR",
        "instrumentType": (md.get("instrument") or {}).get("type", ""),
        "marketStatus": (snap.get("marketStatus") or ""),
    }
    if rules["step"] <= 0:
        rules["step"] = 1.0
    _rules[epic] = rules
    _save()
    return rules


def resolution(tf: str) -> str:
    tf = tf.lower()
    return {"15m": "MINUTE_15", "1h": "HOUR", "4h": "HOUR_4"}.get(tf, "HOUR")


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )


def prices(
    symbol: str, tf: str, start_epoch_ms: int | None, end_epoch_ms: int | None
) -> list[dict]:
    tok = login()
    epic, _ = resolve_epic(symbol, tok)
    res = resolution(tf)
    out = []
    page = 0
    while True:
        params = {"resolution": res, "pageSize": 200}
        if start_epoch_ms:
            params["from"] = _iso(start_epoch_ms)
        if end_epoch_ms:
            params["to"] = _iso(end_epoch_ms)
        if page:
            params["pageNumber"] = page
        r = req("GET", API + f"/prices/{epic}", headers=_headers(tok), params=params)
        js = r.json()
        cs = js.get("prices") or js.get("candles") or []
        for c in cs:
            t = c.get("snapshotTimeUTC") or c.get("snapshotTime") or c.get("date")
            o = c.get("openPrice") or c.get("open") or {}
            h = c.get("highPrice") or c.get("high") or {}
            l = c.get("lowPrice") or c.get("low") or {}
            cl = c.get("closePrice") or c.get("close") or {}
            v = c.get("lastTradedVolume") or c.get("volume") or 0

            def val(x):
                if isinstance(x, dict):
                    return (
                        x.get("mid")
                        if x.get("mid") is not None
                        else x.get("bid") if x.get("bid") is not None else x.get("ask")
                    )
                return x

            out.append(
                {
                    "ts": t,
                    "open": val(o),
                    "high": val(h),
                    "low": val(l),
                    "close": val(cl),
                    "volume": v,
                }
            )
        md = js.get("metadata", {})
        pd = md.get("pageData", {})
        if not pd or pd.get("pageNumber", 0) >= pd.get("totalPages", 0):
            break
        page += 1
        time.sleep(0.05)
    return out
