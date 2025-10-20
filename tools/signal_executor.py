#!/usr/bin/env python3
from __future__ import annotations
import os
from typing import Optional
from tools.capital_client import place_market_order  # olettaa olemassaolon
# Jos teillä on eri nimi funktiolle, vaihda import ja kutsu sen mukaan

def _pos_size(equity: float, risk_pct: float, sl_px: Optional[float], entry_px: float, symbol: str) -> float:
    # Yksinkertainen riskipohjainen positio: risk_pct * equity
    # Jos SL tunnetaan, skaalaa etäisyyden mukaan. Muutoin käytä kiinteää vipua/lot-kokoa env:stä.
    base = equity * risk_pct
    if sl_px and sl_px > 0:
        dist = abs(entry_px - sl_px)
        if dist > 0:
            # arvioitu koko: risk euroissa / dist, ilman vipukäsittelyä (voi lisätä instrumentin sopivaksi)
            return max(base / dist, 0.0)
    # fallback: kiinteä koko
    return float(os.getenv("LIVE_FIXED_SIZE", "1"))

def execute_action(symbol: str, tf: str, action: str, entry_px: float, equity: float,
                   sl_px: Optional[float] = None, tp_px: Optional[float] = None) -> bool:
    """
    Toteuta toimeksianto. Jos sl_px/tp_px on annettu ja LIVE_TP_SL=1, liitä SL/TP.
    Palauta True, jos toimeksianto lähetettiin onnistuneesti.
    """
    try:
        side = "BUY" if action == "BUY" else "SELL"
        risk_pct = float(os.getenv("LIVE_RISK_PCT", "0.01"))  # 1% oletus
        size = _pos_size(equity, risk_pct, sl_px, entry_px, symbol)
        attach = (os.getenv("LIVE_TP_SL", "0") == "1")
        sl = float(sl_px) if (attach and sl_px and sl_px > 0) else None
        tp = float(tp_px) if (attach and tp_px and tp_px > 0) else None

        # Broker-ajo: jos place_market_order tukee SL/TP, välitä ne, muuten ignoroi ylimääräiset
        ok = place_market_order(symbol=symbol, side=side, size=size, price_hint=entry_px, stop_loss=sl, take_profit=tp, tf=tf)
        return bool(ok)
    except Exception as e:
        print(f"[EXEC] failed {symbol} {tf} {action}: {e}", flush=True)
        return False
