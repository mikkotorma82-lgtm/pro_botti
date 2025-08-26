from __future__ import annotations
import os, sys, json, time, uuid, math, typing as t, requests
from dataclasses import dataclass
from pathlib import Path

# === ENV ===
try:
    from tools._dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

BASE = (
    os.getenv("CAPITAL_API_BASE")
    or os.getenv("CAPITAL_BASE_URL")
    or "https://demo-api-capital.backend-capital.com"
).rstrip("/")
API = BASE + "/api/v1"


def _api_key() -> str:
    return os.getenv("CAPITAL_API_KEY") or os.getenv("CAPITAL_KEY", "")


def _headers(extra=None):
    h = {"X-CAP-API-KEY": _api_key(), "Accept": "application/json"}
    if extra:
        h.update(extra)
    return h


def _login():
    r = requests.post(
        API + "/session",
        headers=_headers(),
        json={
            "identifier": os.getenv("CAPITAL_USERNAME")
            or os.getenv("CAPITAL_IDENTIFIER"),
            "password": os.getenv("CAPITAL_PASSWORD"),
            "encryptedPassword": False,
        },
        timeout=30,
    )
    r.raise_for_status()
    return {
        "CST": r.headers.get("CST", ""),
        "X-SECURITY-TOKEN": r.headers.get("X-SECURITY-TOKEN", ""),
    }


# ---- universe loader (sisäinen oletus + yliajo data/universe.yaml) ----
def _default_universe() -> t.List[str]:
    return [
        # FX
        "EURUSD",
        "GBPUSD",
        "USDJPY",
        "USDCHF",
        "USDCAD",
        "AUDUSD",
        "NZDUSD",
        "EURGBP",
        "EURJPY",
        "GBPJPY",
        "EURCHF",
        "AUDJPY",
        "CADJPY",
        "CHFJPY",
        "EURCAD",
        "EURNZD",
        "GBPCAD",
        "GBPCHF",
        # Indices
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
        # Crypto
        "BTCUSDT",
        "ETHUSDT",
        "XRPUSDT",
        "SOLUSDT",
        "ADAUSDT",
        "DOGEUSDT",
        "BNBUSDT",
        "LTCUSDT",
        "SHIBUSDT",
        "AVAXUSDT",
        "DOTUSDT",
        "MATICUSDT",
        "LINKUSDT",
        "TRXUSDT",
        "XLMUSDT",
        "APTUSDT",
        "SUIUSDT",
        # Commodities
        "XAUUSD",
        "XAGUSD",
        "WTI",
        "BRENT",
        "NATGAS",
        # US megacaps
        "AAPL",
        "MSFT",
        "NVDA",
        "AMZN",
        "META",
        "GOOGL",
        "TSLA",
        "AVGO",
        "COST",
        "LLY",
        "JPM",
        "JNJ",
        "V",
        "MA",
        "WMT",
        # EU blue chips
        "SAP",
        "ASML",
        "OR",
        "NESN",
        "TTE",
        "SHEL",
        "NOVN",
        "SIE",
        "AIR",
        "MC",
    ]


def _load_universe() -> t.List[str]:
    y = Path("data/universe.yaml")
    if not y.exists():
        return _default_universe()
    import yaml

    cfg = yaml.safe_load(y.read_text()) or {}
    out = []
    for _, arr in cfg.items():
        if isinstance(arr, list):
            for line in arr:
                if isinstance(line, str):
                    out += [
                        s for s in line.replace(",", " ").split() if s and s[0] != "#"
                    ]
    # poista duplikaatit säilyttäen järjestyksen
    return list(dict.fromkeys(out))


# ---- symbol heuristiikka -> market type filtteri ----
def _wanted_types(sym: str) -> t.Tuple[t.Set[str], t.Set[str]]:
    s = sym.upper()
    if s.endswith("USDT") or s in {"BTCUSD", "ETHUSD", "XRPUSD", "SOLUSD"}:
        return {"CRYPTO"}, {"CRYPTO"}
    if s in {"XAUUSD", "XAGUSD", "WTI", "BRENT", "NATGAS"}:
        return {"COMMODITIES", "COMMODITY"}, {"COMMODITIES", "COMMODITY"}
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
    if len(s) == 6 and s.isalpha():  # EURUSD-tyyli
        return {"CURRENCIES", "FX"}, {"CURRENCIES", "FX"}
    return {"SHARES", "EQUITIES"}, {"SHARES", "EQUITIES"}  # oletus


# ---- caches ----
ECACHE = Path("data/epic_cache.json")
RCACHE = Path("data/rules_cache.json")
ECACHE.parent.mkdir(parents=True, exist_ok=True)
_epic = json.loads(ECACHE.read_text()) if ECACHE.exists() else {}
_rules = json.loads(RCACHE.read_text()) if RCACHE.exists() else {}


def _save():
    ECACHE.write_text(json.dumps(_epic, indent=2, ensure_ascii=False))
    RCACHE.write_text(json.dumps(_rules, indent=2, ensure_ascii=False))


# EPIC-haku tyypin mukaan
def resolve_epic(sym: str, tok: dict) -> t.Tuple[str, dict]:
    s = sym.upper()
    if s in _epic:
        return _epic[s]["epic"], _epic[s]["hit"]
    itypes, mtypes = _wanted_types(s)
    r = requests.get(
        API + "/markets", params={"searchTerm": s}, headers=_headers(tok), timeout=30
    )
    r.raise_for_status()
    items = r.json().get("markets", [])

    def ok(item):
        it = (item.get("instrumentType") or "").upper()
        mt = (item.get("marketType") or "").upper()
        name = (item.get("instrumentName") or "").upper()
        symb = (item.get("symbol") or "").upper()
        return (it in itypes or mt in mtypes) and (
            s == symb or s == name or s == name.replace(" ", "")
        )

    ranked = [x for x in items if ok(x)] or items
    if not ranked:
        raise RuntimeError(f"EPIC not found for {s}")
    hit = ranked[0]
    _epic[s] = {"epic": hit["epic"], "hit": hit}
    _save()
    return hit["epic"], hit


# dealingRules + valuutta
def market_rules(epic: str, tok: dict) -> dict:
    if epic in _rules:
        return _rules[epic]
    r = requests.get(API + f"/markets/{epic}", headers=_headers(tok), timeout=30)
    r.raise_for_status()
    md = r.json()
    dr = md.get("dealingRules") or {}
    snap = md.get("snapshot") or {}
    rules = {
        "min_size": float((dr.get("minDealSize") or {}).get("value", 0) or 0),
        "step": float(
            (dr.get("minDealSizeFractional") or {}).get("value", 0)
            or (dr.get("minStepDistance") or {}).get("value", 0)
            or 1.0
        ),
        "lot_size": float((md.get("instrument") or {}).get("lotSize", 1) or 1),
        "currency": snap.get("currency") or "EUR",
        "instrumentType": (md.get("instrument") or {}).get("type", ""),
    }
    if rules["step"] <= 0:
        rules["step"] = 1.0
    _rules[epic] = rules
    _save()
    return rules


def _quant(size: float, step: float, min_size: float) -> float:
    if step <= 0:
        step = 1.0
    q = math.floor(size / step) * step
    return round(q, 6) if q >= min_size else 0.0


def main():
    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"ok": False, "error": "no_input"}))
        return
    d = json.loads(raw)
    if not {"symbol", "side", "units"}.issubset(d):
        print(json.dumps({"ok": False, "error": "missing_fields", "got": d}))
        return

    live = os.getenv("LIVE_TRADING", "0") == "1"
    tp_r = float(os.getenv("TP_R", "0") or 0)

    tok = _login()
    epic, meta = resolve_epic(d["symbol"], tok)
    rules = market_rules(epic, tok)
    size = _quant(float(d["units"]), rules["step"], rules["min_size"])
    if size <= 0:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "below_min_size",
                    "min_size": rules["min_size"],
                    "step": rules["step"],
                    "preview": {
                        "epic": epic,
                        "direction": d["side"],
                        "size_in": d["units"],
                        "size": size,
                        "market_rules": rules,
                        "note": "DRY-RUN" if not live else "LIVE",
                    },
                },
                ensure_ascii=False,
            )
        )
        return

    payload = {
        "epic": epic,
        "direction": d["side"],
        "size": size,
        "currencyCode": rules["currency"],
        "forceOpen": True,
        "guaranteedStop": False,
    }
    if d.get("stop_abs"):
        payload["stopDistance"] = max(1, int(round(float(d["stop_abs"]))))
    if tp_r and d.get("stop_abs"):
        payload["limitDistance"] = int(round(tp_r * float(d["stop_abs"])))

    preview = {
        "epic": epic,
        "meta": meta,
        "direction": d["side"],
        "size": size,
        "currency": payload["currencyCode"],
        "stop_distance": payload.get("stopDistance"),
        "limit_distance": payload.get("limitDistance"),
        "note": "LIVE" if live else "DRY-RUN",
    }

    if not live:
        print(json.dumps({"ok": True, "preview": preview}, ensure_ascii=False))
        return

    r = requests.post(
        API + "/positions", headers=_headers({**tok}), json=payload, timeout=30
    )
    if r.status_code >= 400:
        try:
            err = r.json()
        except:
            err = {"status": r.status_code, "text": r.text[:300]}
        print(
            json.dumps(
                {"ok": False, "preview": preview, "http_error": err}, ensure_ascii=False
            )
        )
        return
    print(
        json.dumps(
            {"ok": True, "placed": preview, "resp": r.json()}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
