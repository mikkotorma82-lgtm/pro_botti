#!/usr/bin/env python3
from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Tuple, Optional

def simulate_returns(
    df: pd.DataFrame,
    signal: np.ndarray,
    fee_bps: float = 1.0,
    slip_bps: float = 1.5,
    spread_bps: float = 0.5,
    position_mode: str = "longflat",  # "longflat" | "longshort"
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Realistinen toteutus-simulaatio:
    - Käyttää close-hintoja per bar (oikean toteutuksen likiarvo)
    - Kulut kun positio muuttuu: round-trip cost ~ (fee + slip + spread) bps
    - position_mode:
        longflat: pos in {-0, +1}
        longshort: pos in {-1, +1}

    Returns: (per_bar_returns, position)
    """
    px = df["close"].astype(float).values
    n = len(px)
    if signal.shape[0] != n:
        raise ValueError("signal length must match df length")

    # Normalisoi signaali -1/0/1
    sig = np.sign(signal).astype(int)
    if position_mode == "longflat":
        sig[sig < 0] = 0  # ei shortteja

    # Positio alkaa nollasta, siirretään 1 bar eteen (päätös bar t vaikuttaa bar t+1 tuottoon)
    pos = np.zeros(n, dtype=float)
    pos[1:] = sig[:-1]

    # Perusbar-tuotto
    ret = np.zeros(n, dtype=float)
    pct = np.zeros(n, dtype=float)
    pct[1:] = (px[1:] - px[:-1]) / (px[:-1] + 1e-12)
    ret = pct * pos

    # Kustannukset kun positio muuttuu
    # kun pos[t] != pos[t-1], vähennä cost bps bar t:ltä
    costs_bps = fee_bps + slip_bps + spread_bps
    changes = np.zeros(n, dtype=bool)
    changes[1:] = pos[1:] != pos[:-1]
    cost = np.zeros(n, dtype=float)
    cost[changes] = costs_bps / 10000.0
    # kustannus vähentää tuottoa
    ret = ret - cost * np.sign(np.abs(pos))  # kustannus vain jos positio ei ole nolla barilla

    return ret, pos
