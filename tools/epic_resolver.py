# -*- coding: utf-8 -*-
"""EPIC-resolver for Capital.com symbols."""
def resolve_epic(symbol: str) -> str:
    """Palauta Capital EPIC annetulle symbolille:
    1) ENV: CAPITAL_EPIC_<SYMBOL>
    2) provider_capital.SYMBOL_TO_EPIC
    3) fallback: symbol sellaisenaan
    """
    import os
    s = (symbol or "").upper()
    epic = os.environ.get(f"CAPITAL_EPIC_{s}")
    if epic:
        return epic
    try:
        from tools import provider_capital as _pc
        m = getattr(_pc, "SYMBOL_TO_EPIC", {})
        if isinstance(m, dict) and s in m and m[s]:
            return m[s]
    except Exception:
        pass
    return s

def rest_bid_ask(sess, base, epic: str):
    """Hae bid/ask market-snapshotista: /api/v1/markets/{epic}
    Palauttaa (bid, ask) tai (None, None)
    """
    import urllib.parse as _up, math
    url = f"{base}/api/v1/markets/{_up.quote(epic)}"
    r = sess.get(url, timeout=10)
    if r.status_code != 200:
        return (None, None)
    js = r.json() or {}
    snap = js.get("snapshot") or {}
    bid = snap.get("bid")
    ask = snap.get("offer") or snap.get("ask")
    if isinstance(bid, float) and math.isnan(bid): bid = None
    if isinstance(ask, float) and math.isnan(ask): ask = None
    return (bid, ask)
