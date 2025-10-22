#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
sync_positions.py
- Kirjautuu Capital.com API:in (X-CAP-API-KEY + session → CST/X-SECURITY-TOKEN)
- Hakee avoimet positiot (useita fallback-endpointteja)
- Kirjoittaa data/open_positions.json formaattiin:
  {
    "positions": {
      "BTCUSD": {"side":"LONG","size":0.25,"entry_price":67120,"tp":69000,"sl":65800,"pnl_pct":1.8,"reason":""},
      "US500":  {"side":"SHORT","size":1.00, ...}
    }
  }
- Päivittää 5 s välein ja logittaa logs/sync_positions.log
"""

import os, time, json, sys, traceback
from pathlib import Path
from typing import Dict, Any, Optional, List

import requests

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
OUT_PATH = DATA_DIR / "open_positions.json"
LOG_PATH = LOGS_DIR / "sync_positions.log"

DATA_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(f"{ts} {msg}\n")

def getenv_str(name: str, default: str = "") -> str:
    val = os.getenv(name, default)
    return str(val) if val is not None else default

def get_base_url() -> str:
    env = getenv_str("CAPITAL_ENV", "live").lower().strip()
    if env == "demo":
        return "https://demo-api-capital.backend-capital.com"
    return "https://api-capital.backend-capital.com"

def capital_login(session: requests.Session) -> bool:
    base = get_base_url().rstrip("/")
    url = base + "/api/v1/session"
    api_key = getenv_str("CAPITAL_API_KEY").strip()
    identifier = getenv_str("CAPITAL_LOGIN").strip()
    password = getenv_str("CAPITAL_PASSWORD").strip()

    headers = {"X-CAP-API-KEY": api_key, "Content-Type": "application/json"}
    payload = {"identifier": identifier, "password": password}

    r = session.post(url, json=payload, headers=headers, timeout=20)
    # Menestynyt login palauttaa headerit CST ja X-SECURITY-TOKEN
    cst = r.headers.get("CST")
    xst = r.headers.get("X-SECURITY-TOKEN")
    if r.status_code // 100 != 2 or not cst or not xst:
        log(f"[login] FAIL status={r.status_code} body={r.text[:300]}")
        return False

    session.headers.update({
        "X-CAP-API-KEY": api_key,
        "CST": cst,
        "X-SECURITY-TOKEN": xst,
        "Content-Type": "application/json"
    })
    log("[login] OK")
    return True

def try_get_json(session: requests.Session, path: str) -> Optional[Dict[str, Any]]:
    base = get_base_url().rstrip("/")
    url = base + path
    r = session.get(url, timeout=20)
    if r.status_code // 100 != 2:
        log(f"[GET {path}] status={r.status_code} body={r.text[:200]}")
        return None
    try:
        return r.json()
    except Exception:
        log(f"[GET {path}] JSON parse error")
        return None

def fetch_open_positions(session: requests.Session) -> List[Dict[str, Any]]:
    """
    Kokeillaan useita polkuja, koska dokumentaatio-/ympäristöeroja voi olla.
    Palauttaa raakalistan positio-olioita (dict).
    """
    candidates = [
        "/api/v1/positions",                 # yleinen
        "/api/v1/positions?status=OPEN",     # filtteri
        "/api/v1/positions/open",            # vaihtoehtoinen
        "/api/v1/position"                   # joissain asennuksissa yksikkömuotoinen
    ]
    for path in candidates:
        data = try_get_json(session, path)
        if not data:
            continue

        # Normalisoi eri muotoihin
        if isinstance(data, dict):
            if "positions" in data and isinstance(data["positions"], list):
                return data["positions"]
            # joskus {"items": [...]}
            if "items" in data and isinstance(data["items"], list):
                return data["items"]
            # joskus suoraan lista sisällä "data"
            if "data" in data and isinstance(data["data"], list):
                return data["data"]
            # joskus yksittäinen position dict
            if "instrument" in data or "epic" in data or "market" in data:
                return [data]
        if isinstance(data, list):
            return data

    return []

def normalize_position(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Yrittää poimia tiedot eri avainvariaatioista (BUY/SELL/long/short, level/averagePrice jne.)
    """
    # symbol/epic
    symbol = rec.get("epic") or rec.get("instrument") or rec.get("market") or rec.get("symbol")
    if not symbol:
        return None
    symbol = str(symbol).upper()

    # side
    direction = (rec.get("direction") or rec.get("side") or rec.get("position") or "").upper()
    if direction in ("BUY","LONG","+","B"):
        side = "LONG"
    elif direction in ("SELL","SHORT","-","S"):
        side = "SHORT"
    else:
        # joskus boolean-like?
        side = "LONG" if str(direction).startswith("B") else "SHORT" if str(direction).startswith("S") else "-"

    # size
    size = rec.get("size") or rec.get("dealSize") or rec.get("quantity") or 0

    # prices
    entry = rec.get("level") or rec.get("averagePrice") or rec.get("entry") or rec.get("entryPrice")
    tp    = rec.get("limitLevel") or rec.get("takeProfit") or rec.get("tp")
    sl    = rec.get("stopLevel")  or rec.get("stopLoss")   or rec.get("sl")

    # pnl %
    pnl_pct = rec.get("profitLossPercentage") or rec.get("pnlPct") or rec.get("pnl_pct")
    if pnl_pct is None:
        # kokeile laskea jos absoluuttinen profitLoss on saatavilla
        pl = rec.get("profitLoss") or rec.get("pnl") or 0
        try:
            ep = float(entry) if entry else None
            sz = float(size) if size else None
            if ep and sz:
                pnl_pct = float(pl) / (ep * sz) * 100.0
        except Exception:
            pnl_pct = 0.0
    try:
        pnl_pct = float(pnl_pct)
    except Exception:
        pnl_pct = 0.0

    return {
        "symbol": symbol,
        "side": side,
        "size": float(size) if str(size).strip() != "" else 0.0,
        "entry_price": float(entry) if entry not in (None,"") else None,
        "tp": float(tp) if tp not in (None,"") else None,
        "sl": float(sl) if sl not in (None,"") else None,
        "pnl_pct": pnl_pct,
        "reason": ""  # voidaan myöhemmin täyttää signal-engine perusteella
    }

def write_positions(positions: Dict[str, Any]):
    tmp = OUT_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump({"positions": positions}, f, ensure_ascii=False, indent=2)
    tmp.replace(OUT_PATH)

def main_loop():
    session = requests.Session()
    session.headers.update({"User-Agent": "CapitalBot Sync/1.0"})
    if not capital_login(session):
        time.sleep(10)
        return

    # kevyt keep-alive: login uusiksi ~15 min välein
    last_login_ts = time.time()

    while True:
        try:
            if time.time() - last_login_ts > 14*60:
                capital_login(session)
                last_login_ts = time.time()

            raw = fetch_open_positions(session)
            norm_list = []
            for rec in raw:
                try:
                    n = normalize_position(rec)
                    if n: norm_list.append(n)
                except Exception:
                    log("[normalize] " + traceback.format_exc())

            by_symbol = {r["symbol"]: {
                "side": r["side"], "size": r["size"], "entry_price": r["entry_price"],
                "tp": r["tp"], "sl": r["sl"], "pnl_pct": r["pnl_pct"], "reason": r["reason"]
            } for r in norm_list}

            write_positions(by_symbol)
            log(f"[ok] positions={len(by_symbol)} -> {OUT_PATH.name}")
        except Exception:
            log("[loop] " + traceback.format_exc())

        time.sleep(5)

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        pass
