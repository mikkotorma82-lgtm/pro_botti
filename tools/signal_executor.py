#!/usr/bin/env python3
from __future__ import annotations
import os
from typing import Optional, Tuple

from tools.position_sizer import pick_size  # AUTO-tila laskee riskin treenistä

# Yritä tuoda risk_guard apurit; fallback jos puuttuvat
try:
    from tools.risk_guard import can_open_more  # type: ignore
except Exception:
    can_open_more = None  # type: ignore[assignment]

try:
    from tools.risk_guard import todays_realized_R  # type: ignore
except Exception:
    todays_realized_R = None  # type: ignore[assignment]

def _fallback_can_open_more(symbol: str, tf: str, equity: float) -> bool:
    """Päästetään uusi avaus, ellei päivän R ole alle rajan (oletus -3.0 R)."""
    try:
        limit_r = float(os.getenv("RISK_MAX_DAILY_R", "-3.0"))
    except Exception:
        limit_r = -3.0
    try:
        r_today = todays_realized_R() if callable(todays_realized_R) else 0.0  # type: ignore[misc]
    except Exception:
        r_today = 0.0
    if r_today is None:
        r_today = 0.0
    return float(r_today) > float(limit_r)

def _can_open(symbol: str, tf: str, equity: float) -> bool:
    if callable(can_open_more):
        try:
            return bool(can_open_more(symbol, tf, equity))  # type: ignore[misc]
        except Exception:
            pass
    return _fallback_can_open_more(symbol, tf, equity)

def execute_action(symbol: str, tf: str, action: str, price: float, equity: float) -> Optional[Tuple[str, float]]:
    """
    action: BUY / SELL / HOLD
    Palauttaa (side, qty) jos order lähetettiin.
    """
    if action not in ("BUY","SELL"):
        return None
    if not _can_open(symbol, tf, equity):
        return None

    side = "BUY" if action == "BUY" else "SELL"
    qty = pick_size(symbol, tf, price, equity)
    if qty <= 0:
        return None

    try:
        from tools.order_router import route_order
    except Exception:
        route_order = None  # type: ignore[assignment]

    if callable(route_order):
        ok = bool(route_order(symbol=symbol, side=side, qty=qty, tf=tf))  # type: ignore[misc]
        if ok:
            return side, qty
    return None
