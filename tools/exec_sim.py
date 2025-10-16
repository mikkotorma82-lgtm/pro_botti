#!/usr/bin/env python3
from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Tuple

def simulate_returns(
    df: pd.DataFrame,
    signal: np.ndarray,
    fee_bps: float = 1.0,
    slip_bps: float = 1.5,
    spread_bps: float = 0.5,
    position_mode: str = "longflat",  # "longflat" | "longshort"
) -> Tuple[np.ndarray, np.ndarray]:
    px = df["close"].astype(float).values
    n = len(px)
    if signal.shape[0] != n:
        raise ValueError("signal length must match df length")

    sig = np.sign(signal).astype(int)
    if position_mode == "longflat":
        sig[sig < 0] = 0

    pos = np.zeros(n, dtype=float)
    pos[1:] = sig[:-1]

    pct = np.zeros(n, dtype=float)
    pct[1:] = (px[1:] - px[:-1]) / (px[:-1] + 1e-12)
    ret = pct * pos

    costs_bps = fee_bps + slip_bps + spread_bps
    changes = np.zeros(n, dtype=bool)
    changes[1:] = pos[1:] != pos[:-1]
    cost = np.zeros(n, dtype=float)
    cost[changes] = costs_bps / 10000.0
    ret = ret - cost * np.sign(np.abs(pos))
    return ret, pos
