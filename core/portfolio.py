from __future__ import annotations
import numpy as np
import pandas as pd

def rolling_corr_guard(returns_df: pd.DataFrame,
                       lookback: int,
                       max_avg_corr: float,
                       candidates: list[str]) -> list[str]:
    """
    Pidä vähiten keskenään korreloiva alijoukko ehdokkaista.
    """
    if returns_df.shape[0] < lookback or len(candidates) <= 1:
        return candidates
    r = returns_df.tail(lookback).pct_change().dropna().corr()
    chosen: list[str] = []
    for sym in candidates:
        if not chosen:
            chosen.append(sym); continue
        vals = []
        for c in chosen:
            if sym in r.index and c in r.columns:
                vals.append(abs(float(r.loc[sym, c])))
        avg = np.mean(vals) if vals else 0.0
        if not np.isnan(avg) and avg <= max_avg_corr:
            chosen.append(sym)
    return chosen
