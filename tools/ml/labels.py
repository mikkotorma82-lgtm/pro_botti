from __future__ import annotations
import numpy as np
import pandas as pd

def get_daily_vol(close: pd.Series, span: int = 100) -> pd.Series:
    r = np.log(close).diff()
    vol = r.ewm(span=span).std()
    return vol

def apply_triple_barrier(df: pd.DataFrame, pt_mult: float, sl_mult: float, max_holding: int) -> pd.Series:
    """
    df: index time-ordered; must include 'close'
    Returns: label Series (+1 hit TP first, -1 hit SL first, 0 time-out)
    """
    close = df["close"].values
    n = len(df)
    labels = np.zeros(n, dtype=int)
    # simple ATR-like scale: rolling std as proxy
    vola = pd.Series(close, index=df.index).pct_change().rolling(50).std().fillna(method="bfill").values
    for i in range(n - 1):
        entry = close[i]
        pt = entry * (1 + pt_mult * (vola[i] or 0.001))
        sl = entry * (1 - sl_mult * (vola[i] or 0.001))
        j_end = min(n - 1, i + max_holding)
        # scan forward until barrier
        hit = 0
        for j in range(i + 1, j_end + 1):
            px = close[j]
            if px >= pt:
                hit = 1; break
            if px <= sl:
                hit = -1; break
        labels[i] = hit  # 0 if neither hit before j_end
    return pd.Series(labels, index=df.index)
