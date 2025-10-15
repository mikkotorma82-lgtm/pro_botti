#!/usr/bin/env python3
from __future__ import annotations
import pandas as pd
import numpy as np

def pivots(df: pd.DataFrame, left: int = 3, right: int = 3) -> pd.DataFrame:
    """
    Merkitse paikalliset huiput/kuopat (pivot high/low) yksinkertaisella naapurivertailulla.
    left/right = kuinka monta kynttilää molemmin puolin.
    """
    h = df["high"].values
    l = df["low"].values
    n = len(df)
    ph = np.zeros(n, dtype=bool)
    pl = np.zeros(n, dtype=bool)
    for i in range(left, n - right):
        if h[i] == max(h[i-left:i+right+1]):
            ph[i] = True
        if l[i] == min(l[i-left:i+right+1]):
            pl[i] = True
    out = df.copy()
    out["pivot_high"] = ph
    out["pivot_low"]  = pl
    return out

def sr_levels(df: pd.DataFrame, window: int = 300, max_levels: int = 5) -> pd.DataFrame:
    """
    Laske S/R‑tasot viimeisestä window-ikkunasta pivotien mukaan.
    Palauttaa DataFrame, jossa sarakkeet ['level', 'type'] (type: 'S'/'R'), uusimmat ensin.
    """
    x = df.iloc[-window:].copy()
    x = pivots(x, left=3, right=3)
    levels = []
    # Resistance: pivot_high hinnat
    for price in x.loc[x["pivot_high"], "high"].tail(100).tolist():
        levels.append((price, "R"))
    # Support: pivot_low hinnat
    for price in x.loc[x["pivot_low"], "low"].tail(100).tolist():
        levels.append((price, "S"))
    # Klusteroi lähellä olevat tasot yhdeksi (yksinkertainen tolerantti)
    levels = sorted(levels, key=lambda t: t[0])
    clustered = []
    tol = np.mean(x["close"]) * 0.0015  # ~0.15% toleranssi, säädä instrumentin mukaan
    for price, typ in levels:
        if not clustered:
            clustered.append([price, typ, 1])
        else:
            last_p, last_t, cnt = clustered[-1]
            if abs(price - last_p) <= tol and typ == last_t:
                # yhdistä klusteriin keskiarvolla
                new_p = (last_p * cnt + price) / (cnt + 1)
                clustered[-1] = [new_p, last_t, cnt + 1]
            else:
                clustered.append([price, typ, 1])
    # pisteytä klusterit frekvenssin mukaan ja poimi top tasot
    clustered = sorted(clustered, key=lambda t: t[2], reverse=True)[:max_levels]
    return pd.DataFrame({"level": [c[0] for c in clustered], "type": [c[1] for c in clustered]})
