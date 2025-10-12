#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/trade_live.py

Tavoite:
 - Tarjota live-signaalin todennäköisyys (p_up) AI-gatea varten.
 - 1) Yritä käyttää koulutettua mallia (joblib + scaler) ja juuri rakennettuja featureita
 - 2) Jos malli/featuret puuttuvat, käytä varmistettua heuristista fallbackia (EMA/RSI/ATR)

Rajapinnat, joita live_daemon tukee:
 - get_scores(symbol, tf) -> dict {"long": p_up, "short": 1-p_up}
 - predict_signal(symbol, tf) -> sama dict (taaksepäin yhteensopivuus)
 - prob_up(symbol, tf) -> float

Riippuvuudet:
 - pandas, numpy
 - joblib
 - pyarrow (Parquet)
 - (valinnainen) tools.build_features.build_features jos halutaan käyttää samoja featuja kuin trainer
"""

import os
import json
import math
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

# yritä käyttää joblibia mallien lataukseen
try:
    from joblib import load as joblib_load
except Exception:
    joblib_load = None

# yritä hyödyntää samoja featurerakentajia kuin trainer
try:
    from tools.build_features import build_features as build_features_full  # type: ignore
except Exception:
    build_features_full = None  # ei pakollinen, fallback riittää

ROOT = "/root/pro_botti"
MODELS_DIR = f"{ROOT}/models"
HIST_DIR = f"{ROOT}/data/history"

# ----------------- Apurit -----------------
def _meta_path(symbol: str, tf: str) -> str:
    return os.path.join(MODELS_DIR, f"pro_{symbol}_{tf}.json")

def _load_meta(symbol: str, tf: str) -> Dict:
    p = _meta_path(symbol, tf)
    if not os.path.exists(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _load_parquet(symbol: str, tf: str, rows: int = 600) -> Optional[pd.DataFrame]:
    fp = os.path.join(HIST_DIR, f"{symbol}_{tf}.parquet")
    if not os.path.exists(fp):
        return None
    try:
        df = pd.read_parquet(fp)
        if not isinstance(df.index, pd.DatetimeIndex):
            # varmistetaan aikaleimaindeksi jos mahdollista
            if "time" in df.columns:
                df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
                df = df.set_index("time")
        df = df.sort_index()
        if rows and len(df) > rows:
            df = df.iloc[-rows:]
        return df
    except Exception:
        return None

def _safe_float(x, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default

# ----------------- Heuristinen fallback -----------------
def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()

def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0.0)
    down = -delta.clip(upper=0.0)
    gain = up.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    loss = down.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = gain / (loss + 1e-12)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    # odotetaan sarakkeita: high, low, close
    high = df["high"]; low = df["low"]; close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    return atr

def _sigmoid(x: float) -> float:
    # vakaampi sigmoid
    x = max(-10.0, min(10.0, x))
    return 1.0 / (1.0 + math.exp(-x))

def _heuristic_prob_up(df: pd.DataFrame) -> float:
    """
    Pehmeä p_up 0.40..0.60 haarukassa normaalioloissa,
    voi venyä 0.35..0.65 kun signaalit selkeitä.
    Tarkoitus ei ole "treidata heuristiikalla" vaan palvella fallbackina.
    """
    close = df["close"].astype(float)
    ema_fast = _ema(close, 12)
    ema_slow = _ema(close, 48)
    rsi = _rsi(close, 14)
    atr = _atr(df, 14)
    ret = close.pct_change().fillna(0.0)

    # viimeisimmät
    f = ema_fast.iloc[-1]
    s = ema_slow.iloc[-1]
    r = rsi.iloc[-1]
    vol = (atr.iloc[-1] / max(1e-12, close.iloc[-1]))  # ATR/price
    mom = ret.rolling(10).mean().iloc[-1]  # 10-bar momentum

    # normalisointeja
    trend = (f - s) / (abs(s) + 1e-9)              # trendiero
    rsi_c = (r - 50.0) / 25.0                       # keskitetty RSI
    mom_c = mom * 10.0                              # skaalaa momentum
    vol_c = -min(vol, 0.05) * 2.0                   # korkea vol = penalisoidaan hieman

    z = 0.9*trend + 0.6*rsi_c + 0.4*mom_c + 0.3*vol_c
    p = _sigmoid(z)

    # clamp väljemmin, jotta AI-gate voi erotella
    p = max(0.35, min(0.65, p))
    return float(p)

# ----------------- ML polku -----------------
def _guess_model_paths(meta: Dict, symbol: str, tf: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Yritä löytää mallin ja skaalerin polut metadatasta tai oletusnimistä.
    Tuetut avaimet metassa: "model_path", "clf_path", "scaler_path"
    Oletusnimet: models/{symbol}_{tf}.joblib, models/{symbol}_{tf}_scaler.joblib
    """
    clf = meta.get("model_path") or meta.get("clf_path")
    scl = meta.get("scaler_path")

    if clf is None:
        cand = os.path.join(MODELS_DIR, f"{symbol}_{tf}.joblib")
        if os.path.exists(cand):
            clf = cand
    if scl is None:
        cand = os.path.join(MODELS_DIR, f"{symbol}_{tf}_scaler.joblib")
        if os.path.exists(cand):
            scl = cand
    return clf, scl

def _build_last_feature_row(symbol: str, tf: str) -> Optional[pd.DataFrame]:
    """
    Yritä rakentaa sama feature-rivi kuin trainer. Jos tools.build_features on saatavilla,
    käytä sitä koko DataFrameen ja nappaa viimeinen rivi. Muuten palautetaan None.
    """
    if build_features_full is None:
        return None
    df = _load_parquet(symbol, tf, rows=1500)
    if df is None or len(df) < 100:
        return None

    try:
        X, y, feats = build_features_full(df.copy(), tf=tf)  # build_features palauttaa X,y,feat_names
        if hasattr(X, "iloc") and len(X) > 0:
            last_row = X.iloc[[-1]].copy()
            # varmistetaan ettei NaN
            last_row = last_row.replace([np.inf, -np.inf], np.nan).fillna(0.0)
            return last_row
    except Exception:
        pass
    return None

def _predict_with_model(symbol: str, tf: str) -> Optional[float]:
    """
    Lataa meta -> malli + skaaleri -> rakenna viimeinen feature-rivi -> predict_proba -> p_up
    Jos jokin vaihe epäonnistuu, palaa None (fallback käyttöön).
    """
    meta = _load_meta(symbol, tf)
    if not meta:
        return None
    clf_p, scl_p = _guess_model_paths(meta, symbol, tf)
    if clf_p is None or joblib_load is None:
        return None

    try:
        clf = joblib_load(clf_p)
    except Exception:
        return None

    scaler = None
    if scl_p is not None:
        try:
            scaler = joblib_load(scl_p)
        except Exception:
            scaler = None

    X_last = _build_last_feature_row(symbol, tf)
    if X_last is None:
        # viimeinen oljenkorsi: jos build_features ei ole, tee suppea feature-paketti
        df = _load_parquet(symbol, tf, rows=600)
        if df is None or len(df) < 60:
            return None
        # rakentaan pikafeaturet (EMA/RSI/ATR) -> 6-10 halpaa featurea
        c = df["close"].astype(float)
        f = _ema(c, 12); s = _ema(c, 48)
        rs = _rsi(c, 14)
        at = _atr(df, 14)
        mom = c.pct_change().rolling(10).mean()
        vol = at / (c + 1e-12)

        X_last = pd.DataFrame({
            "ema12": [f.iloc[-1]],
            "ema48": [s.iloc[-1]],
            "ema_diff": [(f.iloc[-1] - s.iloc[-1]) / (abs(s.iloc[-1]) + 1e-9)],
            "rsi14": [rs.iloc[-1]],
            "mom10": [mom.iloc[-1]],
            "atr14": [at.iloc[-1]],
            "atrp": [vol.iloc[-1]],
            "ret1": [c.pct_change().iloc[-1]],
        }).replace([np.inf, -np.inf], np.nan).fillna(0.0)

    try:
        Xp = X_last.values
        if scaler is not None:
            Xp = scaler.transform(Xp)
        # predict_proba oletus: sarake 1 on "up"
        if hasattr(clf, "predict_proba"):
            proba = clf.predict_proba(Xp)
            if isinstance(proba, np.ndarray) and proba.ndim == 2 and proba.shape[1] >= 2:
                p_up = float(proba[0, 1])
            else:
                # jos yksiluokka-ongelma (harvinaista) -> käytä decision_function heuristiikkaa
                if hasattr(clf, "decision_function"):
                    z = float(np.ravel(clf.decision_function(Xp))[0])
                    p_up = _sigmoid(z)
                else:
                    # viimeinen fallback: predict-> {0,1}
                    pred = float(np.ravel(clf.predict(Xp))[0])
                    p_up = max(0.01, min(0.99, pred))
        else:
            # decision_function fallback
            if hasattr(clf, "decision_function"):
                z = float(np.ravel(clf.decision_function(Xp))[0])
                p_up = _sigmoid(z)
            else:
                pred = float(np.ravel(clf.predict(Xp))[0])
                p_up = max(0.01, min(0.99, pred))
        # siivous ja clamp
        p_up = max(0.01, min(0.99, p_up))
        return p_up
    except Exception:
        return None

# ----------------- Julkiset rajapinnat -----------------
def prob_up(symbol: str, tf: str) -> Optional[float]:
    """
    Ensisijaisesti mallin p_up; jos ei onnistu, heuristinen p_up.
    Palauttaa float tai None (jos data/laske ei onnistu lainkaan).
    """
    # 1) Malli
    p = _predict_with_model(symbol, tf)
    if isinstance(p, (float, int)) and not (math.isnan(p) or math.isinf(p)):
        return float(p)

    # 2) Heuristinen fallback datasta
    df = _load_parquet(symbol, tf, rows=600)
    if df is None or len(df) < 60 or not all(k in df.columns for k in ("close", "high", "low")):
        return None
    return _heuristic_prob_up(df)

def get_scores(symbol: str, tf: str) -> Dict[str, float]:
    """
    Palauta {"long": p_up, "short": 1-p_up}
    Jos p_up= None -> tyhjä signaali (palautetaan 0.5/0.5 jotta AI-gate pitää HOLD:ina,
    mutta live_daemon logittaa syyn p_up puuttumiseen vain jos _täysin_ None).
    """
    p = prob_up(symbol, tf)
    if p is None:
        # neutral -> AI-gate todennäköisesti HOLD
        return {"long": 0.5, "short": 0.5}
    p = max(0.0, min(1.0, float(p)))
    return {"long": p, "short": 1.0 - p}

def predict_signal(symbol: str, tf: str):
    """Taaksepäin yhteensopiva alias get_scoresille."""
    return get_scores(symbol, tf)


# Pikatesti (ei ajeta palveluna)
if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "US500"
    tf = sys.argv[2] if len(sys.argv) > 2 else "1h"
    s = get_scores(sym, tf)
    print(sym, tf, "->", s)
