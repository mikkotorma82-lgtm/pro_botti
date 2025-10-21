#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from tools.capital_session import capital_get_candles_df

STATE_DIR = Path(__file__).resolve().parents[1] / "state"
REGISTRY_PATH = STATE_DIR / "models_sma.json"

def _load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return {"models": []}
    return json.loads(REGISTRY_PATH.read_text())

def _get_best_n(symbol: str, tf: str) -> Optional[int]:
    reg = _load_registry()
    rows = [m for m in reg.get("models", []) if m.get("symbol") == symbol and m.get("tf") == tf and m.get("strategy") == "SMA"]
    if not rows:
        return None
    # choose latest updated
    rows.sort(key=lambda r: int(r.get("time", 0)), reverse=True)
    return int(rows[0].get("params", {}).get("n", 20))

def _sma_signal(df: pd.DataFrame, n: int) -> str:
    # return 'LONG' or 'FLAT' for last bar
    px = df["close"].astype(float).values
    if len(px) < n + 2:
        return "HOLD"
    sma = pd.Series(px).rolling(n, min_periods=n).mean().values
    prev = px[-2] - (sma[-2] if not np.isnan(sma[-2]) else px[-2])
    last = px[-1] - (sma[-1] if not np.isnan(sma[-1]) else px[-1])
    # cross above → LONG, cross below → FLAT (exit)
    if prev <= 0 and last > 0:
        return "BUY"
    if prev >= 0 and last < 0:
        return "SELL"
    # if above SMA stay long; below stay flat
    return "HOLD"

def next_action(symbol: str, tf: str, lookback: int = 600) -> Tuple[str, Optional[int]]:
    """
    Returns ('BUY'|'SELL'|'HOLD', n) using best n from registry and latest candles from Capital.
    """
    n = _get_best_n(symbol, tf)
    if not n:
        return ("HOLD", None)
    df = capital_get_candles_df(symbol, tf, total_limit=max(lookback, n + 5))
    if df.empty:
        return ("HOLD", n)
    sig = _sma_signal(df, n)
    return sig, n
