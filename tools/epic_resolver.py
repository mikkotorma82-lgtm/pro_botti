# -*- coding: utf-8 -*-
"""EPIC resolver for Capital.com symbols (env-first, no HK50 fallback)."""

import os
import math
import urllib.parse as _up

# Fallback-map kaikille pääindekseille
FALLBACK = {
    "US500": os.getenv("CAPITAL_EPIC_US500", "US500"),
    "US100": os.getenv("CAPITAL_EPIC_US100", "US100"),
    "DE40":  os.getenv("CAPITAL_EPIC_DE40",  "DE40"),
    "UK100": os.getenv("CAPITAL_EPIC_UK100", "UK100"),
    "JP225": os.getenv("CAPITAL_EPIC_JP225", "J225"),  # älä koskaan mapita HK50:een
}

def resolve_epic(symbol: str) -> str:
    """
    Palauta Capital EPIC annetulle symbolille:
      1) Ympäristömuuttuja CAPITAL_EPIC_<SYMBOL>
      2) provider_capital.SYMBOL_TO_EPIC
      3) Fallback-map (yllä)
      4) symbol sellaisenaan
    """
    s = (symbol or "").upper()

    # 1) ympäristöstä
    epic = os.environ.get(f"CAPITAL_EPIC_{s}")
    if epic:
        return epic

    # 2) provider_capital:ista, mutta ilman HK50-mappia
    try:
        from tools import provider_capital as _pc
        m = getattr(_pc, "SYMBOL_TO_EPIC", {})
        if isinstance(m, dict) and s in m and m[s]:
            if str(m[s]).upper() != "HK50":
                return m[s]
    except Exception:
        pass

    # 3) fallback tai symbol sellaisenaan
    return FALLBACK.get(s, s)


def rest_bid_ask(sess, base, epic: str):
    """Hae bid/ask market-snapshotista. Palauttaa (bid, ask) tai (None, None)."""
    url = f"{base}/api/v1/markets/{_up.quote(epic)}"
    try:
        r = sess.get(url, timeout=10)
        if r.status_code != 200:
            return (None, None)
        js = r.json() or {}
        snap = js.get("snapshot") or {}
        bid = snap.get("bid")
        ask = snap.get("offer") or snap.get("ask")
        if isinstance(bid, float) and math.isnan(bid):
            bid = None
        if isinstance(ask, float) and math.isnan(ask):
            ask = None
        return (bid, ask)
    except Exception:
        return (None, None)