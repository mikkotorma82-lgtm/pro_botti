from __future__ import annotations
import os
import re
from typing import Optional, Dict, Any

# Yksinkertainen reititin: käytä capital_client.market_order
from tools import capital_client as cap

def _norm_symbol_for_env_key(symbol: str) -> str:
    """
    'US SPX 500' -> 'USSPX500', 'EUR/USD' -> 'EURUSD'
    """
    return re.sub(r"[^A-Z0-9]", "", symbol.upper())

def to_cap_epic_hint(symbol: str) -> str:
    """
    EPIC-vihje lokitusta varten (poistaa '/' ja välilyönnit).
    HUOM: Varsinainen EPIC resolvoidaan capital_clientissa.
    """
    key = f"CAPITAL_EPIC_{_norm_symbol_for_env_key(symbol)}"
    v = os.environ.get(key)
    if v and v.strip():
        return v.strip()
    return symbol.replace("/", "").replace(" ", "")

def route_order(symbol: str, side: str, qty: float, tf: Optional[str]=None, dry_run: Optional[bool]=None) -> Dict[str, Any]:
    """
    Lähettää markkinatoimeksiannon Capitalille market_orderilla.
    - symbol: näyttönimi (esim 'US SPX 500', 'EUR/USD') tai EPIC-vihje
    - side:   'BUY' / 'SELL'
    - qty:    koko
    - tf:     (valinnainen) ei vaikuta lähetykseen
    - dry_run: jos None, luetaan DRY_RUN env (1 = ei lähetetä)
    """
    s = (side or "").upper()
    if s not in ("BUY", "SELL"):
        raise ValueError(f"route_order: invalid side '{side}'")
    if qty is None or qty <= 0:
        raise ValueError(f"route_order: invalid qty '{qty}'")

    if dry_run is None:
        dry_run = (os.environ.get("DRY_RUN", "1") != "0")

    epic_hint = to_cap_epic_hint(symbol)

    if dry_run:
        return {
            "dry_run": True,
            "exchange": "capital",
            "epic_hint": epic_hint,
            "symbol": symbol,
            "side": s,
            "qty": float(qty),
            "type": "market",
            "tf": tf,
        }

    # market_order huolehtii EPIC-resoluutiosta oikeaksi
    res = cap.market_order(epic=epic_hint, direction=s, size=float(qty))
    return {
        "dry_run": False,
        "exchange": "capital",
        "epic_hint": epic_hint,
        "symbol": symbol,
        "side": s,
        "qty": float(qty),
        "type": "market",
        "tf": tf,
        "result": res,
    }

# Taaksepäin-yhteensopiva alias
def create_market_order(symbol: str, side: str, qty: float, dry_run: Optional[bool]=None) -> Dict[str, Any]:
    return route_order(symbol=symbol, side=side, qty=qty, tf=None, dry_run=dry_run)
