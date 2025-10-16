from __future__ import annotations
import numpy as np
import pandas as pd

def rolling_vola(close: pd.Series, span: int = 50) -> pd.Series:
    r = close.pct_change()
    return r.ewm(span=span, adjust=False).std().fillna(method="bfill")

def label_meta_from_entries(
    df: pd.DataFrame,
    entries_idx: np.ndarray,
    directions: np.ndarray,  # +1 BUY, -1 SELL
    pt_mult: float = 2.0,
    sl_mult: float = 2.0,
    max_holding: int = 48,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Binary meta-label:
      1 -> TP osuu ennen SL:ää
      0 -> SL osuu ensin T:n sisällä T=max_holding; jos ei kumpikaan, 0 (konservatiivinen)
    Toteutus bar-close tasolla ilman intrabar-dataa (live-yhteensopiva).
    """
    close = df["close"].values
    n = len(close)
    vol = rolling_vola(df["close"]).values
    y = np.zeros(len(entries_idx), dtype=int)
    horizon = np.minimum(entries_idx + max_holding, n - 1)

    for k, i in enumerate(entries_idx):
        d = 1 if directions[k] >= 0 else -1
        entry = close[i]
        # Suhteuta barrierit vola:an, lisää pieni minimi, jottei nollavola riko
        vol_i = vol[i] if np.isfinite(vol[i]) and vol[i] > 1e-6 else 1e-3
        tp = entry * (1 + d * pt_mult * vol_i)  # BUY: ylös, SELL: alas (miinus)
        sl = entry * (1 - d * sl_mult * vol_i)  # BUY: alas, SELL: ylös (miinus kääntää suunnan)
        j_end = horizon[k]
        hit = 0
        # Iteroi eteenpäin kunnes yksi osuu
        for j in range(i + 1, j_end + 1):
            px = close[j]
            if d == 1:
                if px >= tp: hit = 1; break
                if px <= sl: hit = 0; break
            else:
                if px <= tp: hit = 1; break
                if px >= sl: hit = 0; break
        y[k] = hit
    return y, horizon
