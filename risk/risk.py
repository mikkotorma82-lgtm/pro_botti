
from dataclasses import dataclass
import pandas as pd
import numpy as np
from utils.misc import bp_to_float
from typing import Dict

@dataclass
class Position:
    symbol: str
    qty: float = 0.0
    avg_price: float = 0.0

def target_position_notional(equity: float, vol_ann: float, risk_cfg, sizing_cfg, signal: int) -> float:
    if signal == 0: return 0.0
    if sizing_cfg.method == "fixed_fraction":
        w = float(sizing_cfg.fixed_fraction)
        return equity * w * signal
    elif sizing_cfg.method == "kelly_fraction":
        # naive Kelly on sign-only: allocate risk_per_trade_bp
        w = bp_to_float(risk_cfg.risk_per_trade_bp)
        return equity * w * signal
    elif sizing_cfg.method == "vol_target":
        # scale such that annualized volatility matches target
        if vol_ann <= 1e-8: return 0.0
        target = float(risk_cfg.volatility_target_annual)
        w = min(target / vol_ann, risk_cfg.max_symbol_weight)
        return equity * w * signal
    else:
        return 0.0
