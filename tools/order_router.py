from __future__ import annotations
import os
import re
from typing import Optional, Dict, Any

from tools import capital_client as cap

def _norm_symbol_for_env_key(symbol: str) -> str:
    """
    Muodostaa environment-avaimen rungon:
      'US SPX 500' -> 'USSPX500'
      'EUR/USD'    -> 'EURUSD'
      'BTC/USD'    -> 'BTCUSD'
    """
    u = symbol.upper()
    # poista kaikki merkit jotka eivät ole A-Z tai 0-9
    return re.sub(r"[^A-Z0-9]", "", u)

def to_cap_epic(symbol: str) -> str:
    """
    EPIC-kartoitus Capitalille:
    1) jos löytyy ympäristömuuttuja CAPITAL_EPIC_<NORM>, käytä sitä
       - esimerkki: CAPITAL_EPIC_USSPX500=US500
    2) muuten poista vinoviivat ja välilyönnit: EUR/USD -> EURUSD
    3) viimeisenä fallback, palauta alkuperäinen ilman vinoviivoja
    """
    # 1) ENV override
    norm = _norm_symbol_for_env_key(symbol)
    env_key = f"CAPITAL_EPIC_{norm}"
    val = os.environ.get(env_key)
    if val and val.strip():
        return val.strip()

    # 2) Poista / ja välilyönnit
    epic = symbol.replace("/", "").replace(" ", "")
    return epic

def create_market_order(symbol: str, side: str, qty: float, dry_run: Optional[bool]=None) -> Dict[str, Any]:
    """
    Taaksepäin-yhteensopiva nimitys. Suositaan route_order()-funktiota.
    """
    return route_order(symbol=symbol, side=side, qty=qty, tf=None, dry_run=dry_run)

def route_order(symbol: str, side: str, qty: float, tf: Optional[str]=None, dry_run: Optional[bool]=None) -> Dict[str, Any]:
    """
    Lähettää markkinatoimeksiannon Capital.comiin.
    - symbol: esim. 'US SPX 500', 'EUR/USD', 'BTC/USD', 'AAPL'
    - side:   'BUY' tai 'SELL'
    - qty:    sopiva size (CFD-koko)
    - tf:     valinnainen, ei vaikuta lähetykseen (raportointiin voi käyttää)
    - dry_run: jos None, luetaan DRY_RUN env (oletus 1 = ei lähetetä)
    Palauttaa dictin; jos dry_run on True, ei lähetä oikeasti tilausta.
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

    # Oikea toimeksianto Capital API:n kautta
    res = cap.market_order(epic=epic, direction=side.upper(), size=float(qty))
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
