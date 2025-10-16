from __future__ import annotations
import os
import re
from typing import Optional, Dict, Any

from tools.capital_client import connect_and_prepare, CapitalClient

# Ylläpidetään yksi ja sama CapitalClient-instanssi
_CC: Optional[CapitalClient] = None

def _client() -> CapitalClient:
    global _CC
    if _CC is None:
        _CC = connect_and_prepare()
    return _CC

def _norm_symbol_for_env_key(symbol: str) -> str:
    """
    Muodostaa environment-avaimen rungon:
      'US SPX 500' -> 'USSPX500'
      'EUR/USD'    -> 'EURUSD'
      'BTC/USD'    -> 'BTCUSD'
    """
    u = symbol.upper()
    return re.sub(r"[^A-Z0-9]", "", u)

def to_cap_epic(symbol: str) -> str:
    """
    EPIC-kartoitus Capitalille:
    1) jos löytyy ympäristömuuttuja CAPITAL_EPIC_<NORM>, käytä sitä
       - esimerkki: CAPITAL_EPIC_USSPX500=US500
    2) muuten poista vinoviivat ja välilyönnit: EUR/USD -> EURUSD
    """
    norm = _norm_symbol_for_env_key(symbol)
    env_key = f"CAPITAL_EPIC_{norm}"
    val = os.environ.get(env_key)
    if val and val.strip():
        return val.strip()
    return symbol.replace("/", "").replace(" ", "")

def route_order(symbol: str, side: str, qty: float, tf: Optional[str]=None, dry_run: Optional[bool]=None) -> Dict[str, Any]:
    """
    Lähettää markkinatoimeksiannon Capital.comiin.
    - symbol: esim. 'US SPX 500', 'EUR/USD', 'BTC/USD', 'AAPL'
    - side:   'BUY' tai 'SELL'
    - qty:    size (CFD-koko)
    - tf:     valinnainen – raportointiin (ei vaikuta lähetykseen)
    - dry_run: jos None, käyttää DRY_RUN env (oletus 1 = ei lähetetä oikeasti)
    """
    if side is None or side.upper() not in ("BUY", "SELL"):
        raise ValueError(f"route_order: invalid side '{side}' (expected BUY/SELL)")
    if qty is None or qty <= 0:
        raise ValueError(f"route_order: invalid qty '{qty}' (must be > 0)")

    if dry_run is None:
        dry_run = (os.environ.get("DRY_RUN", "1") != "0")

    epic = to_cap_epic(symbol)

    if dry_run:
        return {
            "dry_run": True,
            "exchange": "capital",
            "epic": epic,
            "symbol": symbol,
            "side": side.upper(),
            "qty": float(qty),
            "type": "market",
            "tf": tf,
        }

    cli = _client()
    # CapitalClient.place_market käyttää 'symbol' kenttää; annetaan epic-muotoinen string
    res = cli.place_market(symbol=epic, side=side.upper(), size=float(qty))
    # res on jo dict ({"ok":..., "data":..., "order_id":..., "position_id":...})
    return {
        "dry_run": False,
        "exchange": "capital",
        "epic": epic,
        "symbol": symbol,
        "side": side.upper(),
        "qty": float(qty),
        "type": "market",
        "tf": tf,
        "result": res,
    }

def create_market_order(symbol: str, side: str, qty: float, dry_run: Optional[bool]=None) -> Dict[str, Any]:
    """
    Taaksepäin-yhteensopiva alias – suositaan route_order()-funktiota.
    """
    return route_order(symbol=symbol, side=side, qty=qty, tf=None, dry_run=dry_run)
