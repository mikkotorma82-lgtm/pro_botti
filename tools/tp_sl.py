import numpy as np
import pandas as pd

def compute_levels(symbol, side, entry_px, risk_model="default", df=None):
    """
    Laskee TP/SL/Trail-tasot position suuntaan, hintaan ja riskimalliin perustuen.
    Tukee useita riskimalleja: default, ATR, percent.
    """
    # Oletusparametrit
    tp_mult = 1.5
    sl_mult = 1.0
    trail_mult = 0.5

    # Jos ATR-riskimalli, käytä df:ää
    if risk_model.lower() == "atr" and df is not None and len(df) > 14:
        atr = compute_atr(df, 14)[-1]
        sl_dist = atr * sl_mult
        tp_dist = atr * tp_mult
        trail_dist = atr * trail_mult
    elif risk_model.lower() == "percent":
        sl_dist = entry_px * 0.015
        tp_dist = entry_px * 0.025
        trail_dist = entry_px * 0.01
    else:  # default: kiinteä prosentti
        sl_dist = entry_px * 0.01
        tp_dist = entry_px * 0.015
        trail_dist = entry_px * 0.005

    if side.upper() == "BUY":
        sl = entry_px - sl_dist
        tp = entry_px + tp_dist
        trail = entry_px + trail_dist
    elif side.upper() == "SELL":
        sl = entry_px + sl_dist
        tp = entry_px - tp_dist
        trail = entry_px - trail_dist
    else:
        sl = tp = trail = entry_px

    levels = {
        "sl": round(sl, 5),
        "tp": round(tp, 5),
        "trail": round(trail, 5),
    }
    return levels

def compute_atr(df: pd.DataFrame, window=14):
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    tr = np.maximum.reduce([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ])
    atr = tr.rolling(window).mean().fillna(np.mean(tr[:window]))
    return atr.values
