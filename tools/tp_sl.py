# /root/pro_botti/tools/tp_sl.py
# Täysin itsenäinen: TP/SL-profiilit + trailing + breakeven
from typing import Tuple, Dict

def _category(symbol: str) -> str:
    s = symbol.upper()
    if s.endswith("USDT") or s in ("BTCUSD","ETHUSD","SOLUSD","ADAUSD","XRPUSD"):
        return "crypto"
    if s in ("US500","US100","GER40","UK100"):
        return "index"
    if s in ("EURUSD","GBPUSD","USDJPY","USDCHF"):
        return "forex"
    return "equity"

def _risk_profile(symbol: str) -> Dict[str, float]:
    """
    Palauttaa prosenttiset stop/target -parametrit (entryyn nähden).
    Konservatiiviset oletukset; näitä voi myöhemmin ylikirjoittaa mallimetalla.
    """
    cat = _category(symbol)
    if cat == "crypto":
        return {"sl_pct": 0.015, "tp_pct": 0.025, "trail_pct": 0.012, "be_shift_pct": 0.006}
    if cat == "index":
        return {"sl_pct": 0.004, "tp_pct": 0.007, "trail_pct": 0.0035, "be_shift_pct": 0.002}
    if cat == "forex":
        return {"sl_pct": 0.002, "tp_pct": 0.0035, "trail_pct": 0.0015, "be_shift_pct": 0.001}
    # equity
    return {"sl_pct": 0.006, "tp_pct": 0.012, "trail_pct": 0.005, "be_shift_pct": 0.003}

def compute_levels(symbol: str, side: str, entry_px: float) -> Dict[str, float]:
    side = side.upper()
    rp = _risk_profile(symbol)
    e = float(entry_px)
    sl = e * (1 - rp["sl_pct"]) if side == "BUY" else e * (1 + rp["sl_pct"])
    tp = e * (1 + rp["tp_pct"]) if side == "BUY" else e * (1 - rp["tp_pct"])
    return {"sl": sl, "tp": tp, "trail_pct": rp["trail_pct"], "be_shift_pct": rp["be_shift_pct"]}

def trail_update(symbol: str, side: str, entry_px: float, best_px: float, curr_px: float, sl_now: float) -> float:
    """
    Päivittää trailing stopin. Kun liikutaan voitolla, SL siirretään:
    - ensin break-even + be_shift_pct * entry
    - sitten trailing-prosentilla suhteessa parhaaseen hintaan.
    """
    p = compute_levels(symbol, side, entry_px)
    be_px = entry_px * (1 + p["be_shift_pct"]) if side == "BUY" else entry_px * (1 - p["be_shift_pct"])

    if side.upper() == "BUY":
        # jos on edetty vähintään be-shift → nosta vähintään breakeveniin
        if curr_px >= be_px:
            sl_new = max(sl_now, be_px)
            # trailing kohti best_px
            trail = best_px * (1 - p["trail_pct"])
            sl_new = max(sl_new, trail)
            return sl_new
        return sl_now
    else:
        if curr_px <= be_px:
            sl_new = min(sl_now, be_px)
            trail = best_px * (1 + p["trail_pct"])
            sl_new = min(sl_new, trail)
            return sl_new
        return sl_now
