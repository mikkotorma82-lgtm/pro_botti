#!/usr/bin/env python3
from __future__ import annotations
import time
from typing import Optional, Tuple

from tools.position_sizer import pick_size  # oletus: olemassa; muuten tee fallback
from tools.risk_guard import can_open_more  # oletus: olemassa; muuten tee fallback
from tools.order_router import route_order  # oletus: repon oma order router

def execute_action(symbol: str, tf: str, action: str, price: float, equity: float) -> Optional[Tuple[str, float]]:
    """
    action: BUY / SELL / HOLD
    Palauttaa (side, qty) jos lähetettiin orderi.
    """
    if action not in ("BUY","SELL"):
        return None
    if not can_open_more(symbol, tf, equity):
        return None
    side = "BUY" if action=="BUY" else "SELL"
    # riskiperusteinen kokoa (esim 0.5% risk per trade), ATR:ään sidottu stop
    qty = pick_size(symbol, tf, price, equity)
    if qty <= 0:
        return None
    ok = route_order(symbol=symbol, side=side, qty=qty, tf=tf)
    if ok:
        return side, qty
    return None
