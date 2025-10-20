#!/usr/bin/env python3
from __future__ import annotations
import os, inspect
from typing import Optional, Callable, Dict, Any

try:
    import tools.capital_client as capital_client
except Exception:
    capital_client = None

def _pos_size(equity: float, risk_pct: float, sl_px: Optional[float], entry_px: float, symbol: str) -> float:
    base = equity * risk_pct
    if sl_px and sl_px > 0:
        dist = abs(entry_px - sl_px)
        if dist > 0:
            return max(base / dist, 0.0)
    return float(os.getenv("LIVE_FIXED_SIZE", "1"))

def _resolve_broker_func() -> Optional[Callable]:
    if capital_client is None:
        return None
    candidates = [
        "place_market_order",
        "place_market_order_capital",
        "market_order",            # löytyi capital_client.py:stä
        "open_position",
        "send_order",
    ]
    for name in candidates:
        fn = getattr(capital_client, name, None)
        if callable(fn):
            return fn
    return None

def _map_kwargs(fn: Callable, kwargs: Dict[str, Any]) -> Dict[str, Any]:
    try:
        sig = inspect.signature(fn)
        params = sig.parameters
    except Exception:
        return kwargs

    mapped = {}
    alias_map = {
        "symbol": ["instrument", "epic"],
        "side": ["action", "direction"],
        "size": ["qty", "quantity", "units", "volume", "amount"],
        "price_hint": ["price", "priceHint"],
        "stop_loss": ["stopLoss", "sl", "stop_loss_price", "stoploss"],
        "take_profit": ["takeProfit", "tp", "take_profit_price", "takeprofit"],
        "tf": ["timeframe", "resolution"],
    }

    for k, v in kwargs.items():
        if k in params:
            mapped[k] = v
            continue
        assigned = False
        for alias in alias_map.get(k, []):
            if alias in params:
                mapped[alias] = v
                assigned = True
                break
        if not assigned:
            pass

    # Pakolliset oletukset
    for name, p in params.items():
        if p.default is inspect._empty and name not in mapped:
            if name in ("price", "priceHint", "price_hint"):
                mapped[name] = kwargs.get("price_hint")
            elif name in ("qty", "quantity", "units", "volume", "amount", "size"):
                mapped[name] = kwargs.get("size", 1.0)
            elif name in ("action", "direction", "side"):
                mapped[name] = kwargs.get("side", "BUY")
            elif name in ("instrument", "epic", "symbol"):
                mapped[name] = kwargs.get("symbol")
    return mapped

def execute_action(symbol: str, tf: str, action: str, entry_px: float, equity: float,
                   sl_px: Optional[float] = None, tp_px: Optional[float] = None) -> bool:
    try:
        side = "BUY" if action == "BUY" else "SELL"
        risk_pct = float(os.getenv("LIVE_RISK_PCT", "0.01"))
        size = _pos_size(equity, risk_pct, sl_px, entry_px, symbol)
        attach = (os.getenv("LIVE_TP_SL", "0") == "1")
        sl = float(sl_px) if (attach and sl_px and sl_px > 0) else None
        tp = float(tp_px) if (attach and tp_px and tp_px > 0) else None

        broker_fn = _resolve_broker_func()
        if not broker_fn:
            print("[EXEC] No broker order function found in tools.capital_client", flush=True)
            return False

        base_kwargs = dict(symbol= symbol, side= side, size= size, price_hint= entry_px,
                           stop_loss= sl, take_profit= tp, tf= tf)
        call_kwargs = _map_kwargs(broker_fn, base_kwargs)
        ok = broker_fn(**call_kwargs)
        return bool(ok)
    except Exception as e:
        print(f"[EXEC] failed {symbol} {tf} {action}: {e}", flush=True)
        return False
