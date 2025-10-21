import os, math, json, time
from pathlib import Path
from statistics import fmean
from typing import List, Dict, Tuple

import joblib
from tools.live_daemon import capital_rest_login
from tools import epic_resolver

# -------- util --------
def _safe_float(x, default=0.0):
    try: return float(x)
    except Exception: return default

def _ema(vals: List[float], span: int) -> List[float]:
    if not vals or span <= 1: return list(vals or [])
    k = 2.0 / (span + 1.0)
    out=[vals[0]]
    for v in vals[1:]:
        out.append(v*k + out[-1]*(1-k))
    return out

def _rsi(vals: List[float], period: int=14) -> List[float]:
    if len(vals) < period + 1: return [50.0]*len(vals)
    gains, losses = [], []
    for i in range(1, len(vals)):
        d = vals[i] - vals[i-1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = fmean(gains[:period]); avg_l = fmean(losses[:period])
    rsis = [50.0]*period
    for i in range(period, len(gains)):
        avg_g = (avg_g*(period-1)+gains[i])/period
        avg_l = (avg_l*(period-1)+losses[i])/period
        rs = (avg_g/avg_l) if avg_l != 0 else 999.0
        rsis.append(100.0 - (100.0/(1.0+rs)))
    return [50.0] + rsis

def _sigmoid(z: float) -> float:
    try:
        return 1.0/(1.0+math.exp(-z))
    except OverflowError:
        return 0.0 if z < 0 else 1.0

# -------- data --------
def _fetch_prices(symbol: str, resolution="MINUTE", maxn=200) -> Tuple[List[float], List[str]]:
    sess, base = capital_rest_login()
    epic = epic_resolver.resolve_epic(symbol.upper())
    url = f"{base.rstrip('/')}/api/v1/prices/{epic}?resolution={resolution}&max={maxn}"
    r = sess.get(url, timeout=10)
    r.raise_for_status()
    data = r.json()
    closes, ts = [], []
    for row in data.get("prices", []):
        ts.append(row.get("snapshotTimeUTC"))
        c = row.get("closePrice") or {}
        bid = _safe_float(c.get("bid")); ask = _safe_float(c.get("ask"))
        ltp = _safe_float(c.get("lastTraded"))
        if not math.isnan(bid) and not math.isnan(ask):
            closes.append(0.5*(bid+ask))
        elif not math.isnan(ltp):
            closes.append(ltp)
        elif not math.isnan(bid):
            closes.append(bid)
        elif not math.isnan(ask):
            closes.append(ask)
    return closes, ts

# -------- model hooks --------
def _guess_model_paths() -> Dict[str, Path]:
    root = Path(os.getenv("MODEL_DIR", "/root/pro_botti/models"))
    return {"model": root/"model.joblib", "scaler": root/"scaler.joblib"}

def _predict_with_model(symbol: str) -> float | None:
    paths = _guess_model_paths()
    if not all(Path(p).exists() for p in paths.values()):
        return None
    try:
        import numpy as np
        closes, _ = _fetch_prices(symbol, "MINUTE", 200)
        if len(closes) < 30:
            return None
        rsi = _rsi(closes,14)[-1]
        ema12 = _ema(closes,12)[-1]
        ema26 = _ema(closes,26)[-1]
        mom = (closes[-1] - closes[-5]) / max(1e-9, closes[-5])
        X = np.array([[rsi, ema12, ema26, mom]], dtype=float)

        scaler = joblib.load(paths["scaler"])
        model  = joblib.load(paths["model"])
        Xs = scaler.transform(X)

        if hasattr(model, "predict_proba"):
            p = float(model.predict_proba(Xs)[0,1])
        elif hasattr(model, "decision_function"):
            p = _sigmoid(float(model.decision_function(Xs)[0]))
        else:
            return None
        return max(0.01, min(0.99, p))
    except Exception:
        return None

# -------- public API --------
def prob_up(symbol: str) -> float:
    # 1) yritä mallia
    p = _predict_with_model(symbol)
    if isinstance(p, float) and 0.0 <= p <= 1.0:
        return p

    # 2) fallback: EMA/RSI/momentum
    closes, _ = _fetch_prices(symbol, "MINUTE", 200)
    if len(closes) < 30:
        return 0.5
    rsi = _rsi(closes,14)[-1]
    ema12 = _ema(closes,12)[-1]
    ema26 = _ema(closes,26)[-1]
    mom = (closes[-1] - closes[-5]) / max(1e-9, closes[-5])
    z = (rsi-50)/10 + (0.5 if ema12 > ema26 else -0.5) + max(-1, min(1, mom*20))*0.3
    p = _sigmoid(z)
    p = max(0.05, min(0.95, p))
    p = 0.5 + 0.7*(p-0.5)  # pehmennys
    return float(p)

def get_scores(symbol: str) -> Dict[str, float]:
    p = prob_up(symbol)
    return {"long": p, "short": 1.0 - p}

def predict_signal(symbol: str) -> Dict[str, float]:
    # taaksepäinyhteensopiva alias
    return get_scores(symbol)
