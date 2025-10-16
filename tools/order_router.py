from __future__ import annotations
import os
import re
from typing import Optional, Dict, Any

from tools.capital_client import connect_and_prepare, CapitalClient

# Ylläpidetään yksi client
_CC: Optional[CapitalClient] = None

def _client() -> CapitalClient:
    global _CC
    if _CC is None:
        _CC = connect_and_prepare()
    return _CC

def _norm_symbol_for_env_key(symbol: str) -> str:
    u = symbol.upper()
    return re.sub(r"[^A-Z0-9]", "", u)

def to_cap_epic_hint(symbol: str) -> str:
    """
    Palauta vain 'vihje' EPICiksi (poista '/' ja välilyönnit) dry-run tulostukseen.
    Varsinainen EPIC resolvoidaan CapitalClientissä markkinahaulla.
    """
    norm = _norm_symbol_for_env_key(symbol)
    v = os.environ.get(f"CAPITAL_EPIC_{norm}")
    if v and v.strip():
        return v.strip()
    return symbol.replace("/", "").replace(" ", "")

def route_order(symbol: str, side: str, qty: float, tf: Optional[str]=None, dry_run: Optional[bool]=None) -> Dict[str, Any]:
    if side is None or side.upper() not in ("BUY", "SELL"):
        raise ValueError(f"route_order: invalid side '{side}' (expected BUY/SELL)")
    if qty is None or qty <= 0:
        raise ValueError(f"route_order: invalid qty '{qty}' (must be > 0)")

    if dry_run is None:
        dry_run = (os.environ.get("DRY_RUN", "1") != "0")

    epic_hint = to_cap_epic_hint(symbol)

    if dry_run:
        return {
            "dry_run": True,
            "exchange": "capital",
            "epic_hint": epic_hint,
            "symbol": symbol,
            "side": side.upper(),
            "qty": float(qty),
            "type": "market",
            "tf": tf,
        }

    cli = _client()
    # Välitä näyttönimi/symboli – CapitalClient resolvoi EPICin oikeaksi
    res = cli.place_market(symbol=symbol, side=side.upper(), size=float(qty))
    return {
        "dry_run": False,
        "exchange": "capital",
        "epic_hint": epic_hint,
        "symbol": symbol,
        "side": side.upper(),
        "qty": float(qty),
        "type": "market",
        "tf": tf,
        "result": res,
    }

def create_market_order(symbol: str, side: str, qty: float, dry_run: Optional[bool]=None) -> Dict[str, Any]:
    return route_order(symbol=symbol, side=side, qty=qty, tf=None, dry_run=dry_run)
