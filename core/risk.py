from __future__ import annotations
import numpy as np
import pandas as pd

def bars_per_year(tf: str) -> int:
    tf = str(tf).lower()
    if tf.endswith("m"):
        m = int(tf[:-1])
        return (60 // m) * 24 * 252
    if tf.endswith("h"):
        h = int(tf[:-1])
        return (24 // h) * 252
    if tf.endswith("d"):
        return 252
    return 252 * 24  # fallback

def rolling_ann_vol(close: pd.Series, lookback: int, tf: str) -> float:
    ret = close.pct_change().fillna(0.0)
    std = float(ret.rolling(lookback, min_periods=lookback//2).std().iloc[-1])
    bpy = bars_per_year(tf)
    return std * (bpy ** 0.5)

def size_fixed(sign: int, fixed_size: float, max_leverage: float) -> float:
    s = float(fixed_size)
    return float(np.clip(sign * s, -max_leverage, max_leverage))

def size_vol_target(sign: int, close: pd.Series, tf: str, target_ann: float,
                    lookback: int, max_leverage: float) -> float:
    sigma = rolling_ann_vol(close, lookback, tf)
    if sigma <= 0 or not np.isfinite(sigma):
        return 0.0
    scale = target_ann / sigma
    scale = float(np.clip(scale, 0.0, max_leverage))
    return float(sign * scale)

def kelly_fraction(p: float, payoff: float) -> float:
    # f* = p - (1-p)/R, clip <0 to 0 (ei short-kelly tässä)
    if payoff <= 0:
        return 0.0
    f = p - (1.0 - p) / payoff
    return float(max(0.0, f))

def size_kelly(sign: int, p_for_sign: float, payoff: float, max_leverage: float,
               min_prob: float) -> float:
    if p_for_sign < float(min_prob):
        return 0.0
    f = kelly_fraction(p_for_sign, payoff)
    f = float(np.clip(f, 0.0, max_leverage))
    return float(sign * f)

def compute_size(cfg_risk: dict, sign: int, proba_map: dict, close: pd.Series, tf: str) -> float:
    mode = (cfg_risk.get("mode") or "fixed").lower()
    max_lev = float(cfg_risk.get("max_leverage", 3.0))
    if sign == 0:
        return 0.0

    if mode == "fixed":
        return size_fixed(sign, float(cfg_risk.get("fixed_size", 1.0)), max_lev)

    if mode == "vol_target":
        return size_vol_target(
            sign=sign,
            close=close,
            tf=tf,
            target_ann=float(cfg_risk.get("vol_target_annual", 0.20)),
            lookback=int(cfg_risk.get("lookback_bars", 200)),
            max_leverage=max_lev,
        )

    if mode == "kelly":
        p = float(proba_map.get(sign, 0.0))
        return size_kelly(
            sign=sign,
            p_for_sign=p,
            payoff=float(cfg_risk.get("kelly_payoff", 1.0)),
            max_leverage=max_lev,
            min_prob=float(cfg_risk.get("min_prob", 0.5)),
        )

    # default fallback
    return size_fixed(sign, float(cfg_risk.get("fixed_size", 1.0)), max_lev)
