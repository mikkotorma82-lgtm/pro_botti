from __future__ import annotations
import os, re
from pathlib import Path
from typing import Optional, Tuple
import numpy as np
import pandas as pd
from joblib import load
from tools.ml.features import compute_features

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state"
META_DIR = STATE / "models_meta"
META_DIR.mkdir(parents=True, exist_ok=True)
META_REG = STATE / "models_meta.json"

_model_cache: dict[str, Tuple[object, dict]] = {}

def _safe_key(symbol: str, tf: str) -> str:
    k = f"{symbol}__{tf}"
    return re.sub(r"[^A-Za-z0-9_.-]", "", k)

def _load_meta(symbol: str, tf: str) -> Optional[Tuple[object, dict]]:
    k = _safe_key(symbol, tf)
    if k in _model_cache:
        return _model_cache[k]
    path = META_DIR / f"{k}.joblib"
    if not path.exists() or not META_REG.exists():
        return None
    try:
        model = load(path)
        import json
        reg = json.loads(META_REG.read_text())
        row = next((r for r in reg.get("models", []) if r.get("key") == k), None)
        if not row:
            return None
        _model_cache[k] = (model, row)
        return _model_cache[k]
    except Exception:
        return None

def should_take_trade(symbol: str, tf: str, action: str, df: pd.DataFrame) -> Tuple[bool, float]:
    """
    Palauttaa (ok, p) – ok=True jos meta-suodatin hyväksyy kaupan.
    action: 'BUY' / 'SELL'
    """
    if os.getenv("META_ENABLED", "1") != "1":
        return True, 1.0

    got = _load_meta(symbol, tf)
    if not got:
        # Jos vaaditaan meta-malli, estä kauppa kun mallia ei löydy
        if os.getenv("META_REQUIRED", "0") == "1":
            return False, 0.0
        # Muuten älä estä
        return True, 1.0

    model, row = got
    feats = compute_features(df).iloc[-1:].copy()
    feats = feats.replace([np.inf, -np.inf], np.nan).fillna(method="ffill").fillna(method="bfill").fillna(0.0)
    try:
        proba = float(model.predict_proba(feats)[:, 1][0])
    except Exception:
        p = float(model.predict(feats)[0])
        proba = max(0.0, min(1.0, p))

    thr = float(row.get("threshold", float(os.getenv("META_THRESHOLD", "0.6"))))
    if action == "SELL":
        thr = float(row.get("threshold_sell", thr))
    return (proba >= thr), proba
