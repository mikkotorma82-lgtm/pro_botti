#!/usr/bin/env python3
from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Dict, Any

from tools.strategies_pack import signal_sma, signal_ema, signal_rsi, signal_macd

def consensus_signal(df: pd.DataFrame, cfg: Dict[str, Any]) -> np.ndarray:
    """
    cfg:
      weights: {"sma":1.0,"ema":1.0,"rsi":0.5,"macd":1.0}
      params:
        sma_n: 20
        ema_n: 21
        rsi_n: 14; rsi_low:30; rsi_high:70
        macd_fast:12; macd_slow:26; macd_sig:9
      threshold: 0.5  (sum-weight > thr => +1, < -thr => -1, else 0)
    """
    w = cfg.get("weights", {"sma": 1.0, "ema": 1.0, "rsi": 0.5, "macd": 1.0})
    p = cfg.get("params", {})
    thr = float(cfg.get("threshold", 0.5))

    parts = []
    if w.get("sma", 0) != 0:
        parts.append(w["sma"] * signal_sma(df, int(p.get("sma_n", 20))))
    if w.get("ema", 0) != 0:
        parts.append(w["ema"] * signal_ema(df, int(p.get("ema_n", 21))))
    if w.get("rsi", 0) != 0:
        parts.append(w["rsi"] * signal_rsi(df, int(p.get("rsi_n", 14)), p.get("rsi_low", 30.0), p.get("rsi_high", 70.0)))
    if w.get("macd", 0) != 0:
        parts.append(w["macd"] * signal_macd(df, int(p.get("macd_fast", 12)), int(p.get("macd_slow", 26)), int(p.get("macd_sig", 9))))

    if not parts:
        return np.zeros(len(df), dtype=float)

    s = np.sum(parts, axis=0) / (np.sum(np.abs(list(w.values()))) + 1e-12)
    sig = np.zeros_like(s)
    sig[s > thr] = 1.0
    sig[s < -thr] = -1.0
    return sig
