#!/usr/bin/env python3
from __future__ import annotations
import os, json, time
from pathlib import Path
from typing import Dict, Any, List, Tuple

import numpy as np
import pandas as pd

from tools.capital_session import capital_rest_login, capital_get_candles_df
from tools.exec_sim import simulate_returns
from tools.consensus_engine import consensus_signal
from tools.support_resistance import pivots
from tools.symbol_resolver import read_symbols  # <-- päivitys

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
REG_PATH = STATE_DIR / "models_pro.json"

DEFAULT_TFS = ["15m", "1h", "4h"]

# ... (muut osat ennallaan, vain symbolien luku muuttuu)
def main():
    capital_rest_login()
    symbols = read_symbols()
    tfs = [s.strip() for s in (os.getenv("TRAIN_TFS") or "").split(",") if s.strip()] or DEFAULT_TFS
    # ... jatkuu kuten aiemmin
