#!/usr/bin/env python3
feat/meta-simplify-and-fix
from __future__ import annotations
import os, json, time, re, warnings
from pathlib import Path
from typing import Dict, Any, List, Tuple
=======
"""
Wrapper for meta ensemble training to provide train_symbol_tf function.
This serves as the default trainer for META_TRAINER_PATH.
"""
from __future__ import annotations
import os
import json
import time
import warnings
import re
from pathlib import Path
from typing import Dict, Any, List, Tuple

main
import numpy as np
import pandas as pd
from joblib import dump

feat/meta-simplify-and-fix
# Project imports (present in this repo as used by tools/train_meta_ens.py)
from tools.capital_session import capital_rest_login, capital_get_candles_df
from tools.consensus_engine import consensus_signal
from tools.ml.features import compute_features
from tools.ml.labels import label_meta_from_entries
from tools.ml.purged_cv import PurgedTimeSeriesSplit
from tools.ml.asset_class import resolve_asset_class

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state"; STATE.mkdir(parents=True, exist_ok=True)
META_DIR = STATE / "models_meta"; META_DIR.mkdir(parents=True, exist_ok=True)
META_REG = STATE / "models_meta.json"
PRO_REG  = STATE / "models_pro.json"
=======
warnings.filterwarnings("ignore")

# Optional dependencies flags
_sklearn_available = None
_xgb_available = None
_lgbm_available = None
_optuna_available = None

def _check_sklearn() -> bool:
    global _sklearn_available
    if _sklearn_available is None:
        try:
            from sklearn.ensemble import GradientBoostingClassifier  # noqa: F401
            from sklearn.linear_model import LogisticRegression       # noqa: F401
            _sklearn_available = True
        except Exception:
            _sklearn_available = False
    return bool(_sklearn_available)

def _check_xgb() -> bool:
    global _xgb_available
    if _xgb_available is None:
        try:
            import xgboost as xgb  # noqa: F401
            _xgb_available = True
        except Exception:
            _xgb_available = False
    return bool(_xgb_available)

def _check_lgbm() -> bool:
    global _lgbm_available
    if _lgbm_available is None:
        try:
            import lightgbm as lgb  # noqa: F401
            _lgbm_available = True
        except Exception:
            _lgbm_available = False
    return bool(_lgbm_available)

def _check_optuna() -> bool:
    global _optuna_available
    if _optuna_available is None:
        try:
            import optuna  # noqa: F401
            _optuna_available = True
        except Exception:
            _optuna_available = False
    return bool(_optuna_available)

# Imports guarded behind try/except so adapter degrades gracefully
try:
    from tools.capital_session import capital_rest_login, capital_get_candles_df
    _capital_available = True
except Exception:
    _capital_available = False
    capital_rest_login = None  # type: ignore
    capital_get_candles_df = None  # type: ignore

try:
    from tools.ml.features import compute_features
    from tools.ml.labels import label_meta_from_entries
    from tools.ml.purged_cv import PurgedTimeSeriesSplit
    from tools.ml.asset_class import resolve_asset_class
    _ml_tools_available = True
except Exception:
    _ml_tools_available = False

try:
    from tools.consensus_engine import consensus_signal
    _consensus_available = True
except Exception:
    _consensus_available = False

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state"
STATE.mkdir(parents=True, exist_ok=True)
META_DIR = STATE / "models_meta"
META_DIR.mkdir(parents=True, exist_ok=True)
META_REG = STATE / "models_meta.json"
PRO_REG = STATE / "models_pro.json"
main

def _safe_key(symbol: str, tf: str) -> str:
    k = f"{symbol}__{tf}"
    return re.sub(r"[^A-Za-z0-9_.-]", "", k)

def _load_pro_config(symbol: str, tf: str) -> Dict[str, Any]:
    """Load latest CONSENSUS PRO config for a symbol/tf pair from state/models_pro.json."""
    if not PRO_REG.exists():
        return {}
    try:
        obj = json.loads(PRO_REG.read_text() or '{"models":[]}')
    except Exception:
        return {}
    rows = [r for r in obj.get("models", []) if r.get("symbol")==symbol and r.get("tf")==tf and r.get("strategy")=="CONSENSUS"]
    if not rows:
        return {}
    rows.sort(key=lambda r: int(r.get("trained_at", 0)), reverse=True)
    return rows[0].get("config") or {}

def _entry_points(df: pd.DataFrame, cfg: Dict[str, Any]) -> Tuple[np.ndarray, np.ndarray]:
        rows = [
            r for r in obj.get("models", [])
            if r.get("symbol") == symbol and r.get("tf") == tf and r.get("strategy") == "CONSENSUS"
        ]
        if not rows:
            return {}
        rows.sort(key=lambda r: int(r.get("trained_at", 0)), reverse=True)
        return rows[0].get("config") or {}
    except Exception:
        return {}

def _entry_points(df: pd.DataFrame, cfg: Dict[str, Any]) -> Tuple[np.ndarray, np.ndarray]:
    """Compute entry indices and directions from consensus signal."""
    if not _consensus_available:
        raise RuntimeError("consensus_engine not available")
    sig = consensus_signal(df, cfg)
    s = pd.Series(sig, index=df.index)
    prev = s.shift(1).fillna(0)
    buy = (prev <= 0) & (s > 0)
    sell = (prev >= 0) & (s < 0)
    idx = np.where((buy | sell).values)[0]
    dirs = np.where(buy.values[idx], 1, -1)
    return idx, dirs

def _purged_pf(p_list: List[np.ndarray], y_list: List[np.ndarray], thr: float) -> float:
    TP, FP = 0, 0
    for p,y in zip(p_list,y_list):
        yhat = (p >= thr).astype(int)
        TP += int(((yhat==1)&(y==1)).sum())
        FP += int(((yhat==1)&(y==0)).sum())
    return TP / (FP + 1.0)

def _cv_preds(model, X: pd.DataFrame, y: np.ndarray, splits: int, embargo: int) -> Tuple[List[np.ndarray], List[np.ndarray]]:
    """Purged profit factor for a set of CV predictions."""
    TP, FP = 0, 0
    for p, y in zip(p_list, y_list):
        yhat = (p >= thr).astype(int)
        TP += int(((yhat == 1) & (y == 1)).sum())
        FP += int(((yhat == 1) & (y == 0)).sum())
    return TP / (FP + 1.0)

def _features_for_class(asset_class: str) -> List[str]:
    """Select default feature set per asset class."""
    ac = asset_class
    if ac == "crypto":
        return ["sma_diff", "ema_diff", "rsi14", "macd_hist", "atr14", "obv"]
    if ac == "index":
        return ["ema_diff", "rsi14", "adx14", "vola50", "atr14"]
    if ac == "stock":
        return ["ema_diff", "rsi14", "stoch_k", "obv", "atr14"]
    if ac in ("metal", "energy", "fx"):
        return ["ema_diff", "rsi14", "atr14", "vola50", "rng_pct"]
    return ["ema_diff", "rsi14", "vola50", "rng_pct"]

def _cv_preds(model, X: pd.DataFrame, y: np.ndarray, splits: int, embargo: int) -> Tuple[List[np.ndarray], List[np.ndarray]]:
    """Cross-validated predictions with PurgedTimeSeriesSplit."""
    if not _ml_tools_available:
        raise RuntimeError("ML tools not available")
    cv = PurgedTimeSeriesSplit(n_splits=splits, embargo=embargo)
    idx = np.arange(len(X))
    p_list: List[np.ndarray] = []
    y_list: List[np.ndarray] = []
    for tr, te in cv.split(idx):
        if len(np.unique(y[tr]))<2 or len(np.unique(y[te]))<2:
            continue
        m = model.__class__(**getattr(model, "get_params", lambda: {})())
        if hasattr(m, "random_state"):
            try: m.random_state = 42
            except Exception: pass
        m.fit(X.iloc[tr], y[tr])
        try:
            p = m.predict_proba(X.iloc[te])[:,1]
        except Exception:
            p = m.predict(X.iloc[te]).astype(float)
            p = np.clip(p, 0.0, 1.0)
        p_list.append(p.astype(float)); y_list.append(y[te].astype(int))
    return p_list, y_list

def _optuna_ensemble(pdict: Dict[str, List[np.ndarray]], y_list: List[np.ndarray], base_thr: float = 0.6) -> Tuple[Dict[str,float], float, float]:
    names = sorted(pdict.keys()); k = len(names)
    try:
        import optuna
    except Exception:
        optuna = None
    if not optuna or k == 0:
        if k == 0:
            return {}, base_thr, 0.0
        w = {n: 1.0/k for n in names}
        p_ens = [sum(w[n]*pdict[n][i] for n in names) for i in range(len(y_list))]
        return w, base_thr, float(_purged_pf(p_ens, y_list, base_thr))
    def make_ens(wv: List[float]) -> List[np.ndarray]:
        s = sum(wv) + 1e-9; wn = [x/s for x in wv]
        return [sum(wn[j]*pdict[names[j]][i] for j in range(k)) for i in range(len(y_list))]
    study = optuna.create_study(direction="maximize", study_name="meta_ensemble")
        if len(np.unique(y[tr])) < 2 or len(np.unique(y[te])) < 2:
            continue
        m = model.__class__(**getattr(model, "get_params", lambda: {})())
        if hasattr(m, "random_state"):
            try:
                m.random_state = 42
            except Exception:
                pass
        m.fit(X.iloc[tr], y[tr])
        try:
            p = m.predict_proba(X.iloc[te])[:, 1]
        except Exception:
            p = m.predict(X.iloc[te]).astype(float)
            p = np.clip(p, 0.0, 1.0)
        p_list.append(p.astype(float))
        y_list.append(y[te].astype(int))
    return p_list, y_list

def _optuna_ensemble(
    pdict: Dict[str, List[np.ndarray]],
    y_list: List[np.ndarray],
    base_thr: float = 0.6
) -> Tuple[Dict[str, float], float, float]:
    """Optimize ensemble weights with Optuna; falls back to equal weights if unavailable."""
    names = sorted(pdict.keys())
    k = len(names)

    if k == 0:
        return {}, base_thr, 0.0

    if not _check_optuna():
        w = {n: 1.0 / k for n in names}
        p_ens = [sum(w[n] * pdict[n][i] for n in names) for i in range(len(y_list))]
        return w, base_thr, float(_purged_pf(p_ens, y_list, base_thr))

    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def make_ens(wv: List[float]) -> List[np.ndarray]:
        s = sum(wv) + 1e-9
        wn = [x / s for x in wv]
        return [sum(wn[j] * pdict[names[j]][i] for j in range(k)) for i in range(len(y_list))]

    study = optuna.create_study(direction="maximize", study_name="meta_ensemble")

    def objective(trial: "optuna.Trial") -> float:
        ws = [trial.suggest_float(f"w_{n}", 0.0, 1.0) for n in names]
        thr = trial.suggest_float("thr", 0.50, 0.80, step=0.02)
        p_ens = make_ens(ws)
        return float(_purged_pf(p_ens, y_list, thr))
    study.optimize(objective, n_trials=int(os.getenv("ENS_TUNER_TRIALS","60")), show_progress_bar=False)
    best = study.best_params
    ws = [best.get(f"w_{n}", 1.0) for n in names]; s = sum(ws) + 1e-9; wn = [x/s for x in ws]
    w = {names[j]: float(wn[j]) for j in range(k)}
    thr = float(best.get("thr", base_thr))
    p_ens = [sum(w[n]*pdict[n][i] for n in names) for i in range(len(y_list))]
    score = float(_purged_pf(p_ens, y_list, thr))
    return w, thr, score

def train_symbol_tf(symbol: str, timeframe: str, ens_pf: float = 1.0, thr: float = 0.6, models: List[str] | None = None, **kwargs) -> Dict[str, Any]:
    """
    Train META models for a single (symbol, timeframe) and update registry.
    Returns metrics dict for orchestration.
    """
    capital_rest_login()

    # Config/env (align with train_meta_ens.py)

    study.optimize(objective, n_trials=int(os.getenv("ENS_TUNER_TRIALS", "60")), show_progress_bar=False)
    best = study.best_params
    ws = [best.get(f"w_{n}", 1.0) for n in names]
    s = sum(ws) + 1e-9
    wn = [x / s for x in ws]
    w = {names[j]: float(wn[j]) for j in range(k)}
    thr = float(best.get("thr", base_thr))
    p_ens = [sum(w[n] * pdict[n][i] for n in names) for i in range(len(y_list))]
    score = float(_purged_pf(p_ens, y_list, thr))
    return w, thr, score

def train_symbol_tf(
    symbol: str,
    timeframe: str,
    ens_pf: float = 1.0,
    thr: float = 0.6,
    models: List[str] | None = None
) -> Dict[str, Any]:
    """
    Train META ensemble models for a single symbol/timeframe and update registry.

    Returns:
      - success metrics dict, or {"error": "..."} if preconditions are not met.
    """
    if models is None:
        models = ["gbdt", "lr", "xgb", "lgbm"]

    # Dependency checks
    if not _capital_available:
        return {"error": "capital_tools_unavailable", "symbol": symbol, "tf": timeframe}
    if not _ml_tools_available:
        return {"error": "ml_tools_unavailable", "symbol": symbol, "tf": timeframe}
    if not _check_sklearn():
        return {"error": "sklearn_unavailable", "symbol": symbol, "tf": timeframe}

    # Capital login
    capital_rest_login()

    # Config/env parity with tools/train_meta_ens.py
    max_total = int(os.getenv("TRAIN_MAX_TOTAL", "10000"))
    page_size = int(os.getenv("TRAIN_PAGE_SIZE", "200"))
    sleep_sec = float(os.getenv("TRAIN_PAGE_SLEEP", "1.5"))
    pt_mult = float(os.getenv("TB_PT_MULT", "2.0"))
    sl_mult = float(os.getenv("TB_SL_MULT", "2.0"))
    max_hold = int(os.getenv("TB_MAX_HOLD", "48"))
    cv_splits = int(os.getenv("META_CV_SPLITS", "5"))
    embargo = int(os.getenv("META_EMBARGO", str(max_hold)))
    decay = float(os.getenv("TIME_DECAY", "0.995"))

    model_list = [m.strip() for m in (",".join(models) if models else os.getenv("META_MODELS","gbdt,xgb,lgbm,lr")).split(",") if m.strip()]

    # Optional availability checks (xgb, lgbm)
    if "xgb" in model_list:
        try: import xgboost as xgb  # noqa
        except Exception: model_list = [m for m in model_list if m!="xgb"]
    if "lgbm" in model_list:
        try: import lightgbm as lgb  # noqa
        except Exception: model_list = [m for m in model_list if m!="lgbm"]

    # Base config for consensus entries
    cfg = _load_pro_config(symbol, timeframe)
    if not cfg:
        raise RuntimeError(f"no base config for {symbol} {timeframe}; train consensus PRO first")

    # Data
    df = capital_get_candles_df(symbol, timeframe, total_limit=max_total, page_size=page_size, sleep_sec=sleep_sec)
    if df.empty or len(df) < 600:
        raise RuntimeError(f"insufficient data {symbol} {timeframe} ({len(df)})")

    feats_all = compute_features(df).replace([np.inf,-np.inf], np.nan).ffill().bfill().fillna(0.0)
    idx, dirs = _entry_points(df, cfg)
    if len(idx) < 50:
        raise RuntimeError(f"too few entries {symbol} {timeframe} ({len(idx)})")

    asset_class = resolve_asset_class(symbol)

    # feature columns per asset class (mirror of train_meta_ens defaults)
    def _features_for_class(ac: str) -> List[str]:
        if ac == "crypto":
            return ["sma_diff","ema_diff","rsi14","macd_hist","atr14","obv"]
        if ac == "index":
            return ["ema_diff","rsi14","adx14","vola50","atr14"]
        if ac == "stock":
            return ["ema_diff","rsi14","stoch_k","obv","atr14"]
        if ac in ("metal","energy","fx"):
            return ["ema_diff","rsi14","atr14","vola50","rng_pct"]
        return ["ema_diff","rsi14","vola50","rng_pct"]

    want_cols = _features_for_class(asset_class)
    X = feats_all.iloc[idx].reindex(columns=want_cols).fillna(0.0)
    y,_ = label_meta_from_entries(df, idx, dirs, pt_mult=pt_mult, sl_mult=sl_mult, max_holding=max_hold)

    n = len(X)
    weights = (decay ** (np.arange(n)[::-1])).astype(float)

    models_trained: Dict[str, Any] = {}
    cv_pl: Dict[str, List[np.ndarray]] = {}
    cv_yl: List[np.ndarray] | None = None

    # Train GBDT
    if "gbdt" in model_list:
    # Base PRO config for consensus entries
    cfg = _load_pro_config(symbol, timeframe)
    if not cfg:
        return {"error": "no_base_config", "symbol": symbol, "tf": timeframe}

    # Data fetch
    df = capital_get_candles_df(symbol, timeframe, total_limit=max_total, page_size=page_size, sleep_sec=sleep_sec)
    if df.empty or len(df) < 600:
        return {"error": "insufficient_data", "symbol": symbol, "tf": timeframe, "rows": int(len(df))}

    # Features
    feats_all = compute_features(df).replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0.0)

    # Entry points
    idx, dirs = _entry_points(df, cfg)
    if len(idx) < 50:
        return {"error": "too_few_entries", "symbol": symbol, "tf": timeframe, "entries": int(len(idx))}

    # Feature selection
    asset_class = resolve_asset_class(symbol)
    want_cols = _features_for_class(asset_class)
    X = feats_all.iloc[idx].reindex(columns=want_cols).fillna(0.0)
    y, _ = label_meta_from_entries(df, idx, dirs, pt_mult=pt_mult, sl_mult=sl_mult, max_holding=max_hold)

    # Time-decay weights
    n = len(X)
    weights = (decay ** (np.arange(n)[::-1])).astype(float)

    # Filter available models
    available_models: List[str] = []
    for m in models:
        if m in ("gbdt", "lr") and _check_sklearn():
            available_models.append(m)
        elif m == "xgb" and _check_xgb():
            available_models.append(m)
        elif m == "lgbm" and _check_lgbm():
            available_models.append(m)

    if not available_models:
        return {"error": "no_models_available", "symbol": symbol, "tf": timeframe}

    trained_models: Dict[str, Any] = {}
    cv_pl: Dict[str, List[np.ndarray]] = {}
    cv_yl: List[np.ndarray] | None = None

    # GBDT
    if "gbdt" in available_models:
        from sklearn.ensemble import GradientBoostingClassifier
        gbdt = GradientBoostingClassifier(random_state=42)
        gbdt.fit(X, y, sample_weight=weights)
        dump(gbdt, META_DIR / f"{_safe_key(symbol, timeframe)}__gbdt.joblib")
        p_list, y_list = _cv_preds(gbdt, X, y, cv_splits, embargo)
        models_trained["gbdt"] = True; cv_pl["gbdt"] = p_list; cv_yl = y_list

    # Train LR
    if "lr" in model_list:
        trained_models["gbdt"] = True
        cv_pl["gbdt"] = p_list
        cv_yl = y_list

    # Logistic Regression
    if "lr" in available_models:
        from sklearn.linear_model import LogisticRegression
        lr = LogisticRegression(max_iter=200)
        lr.fit(X, y, sample_weight=weights)
        dump(lr, META_DIR / f"{_safe_key(symbol, timeframe)}__lr.joblib")
        p_list, y_list = _cv_preds(lr, X, y, cv_splits, embargo)
        models_trained["lr"] = True; cv_pl["lr"] = p_list; cv_yl = y_list

    # Train XGBoost
    if "xgb" in model_list:
        import xgboost as xgb
        xgbm = xgb.XGBClassifier(
            n_estimators=200, max_depth=4, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
        trained_models["lr"] = True
        cv_pl["lr"] = p_list
        cv_yl = y_list

    # XGBoost
    if "xgb" in available_models:
        import xgboost as xgb
        xgbm = xgb.XGBClassifier(
            n_estimators=200, max_depth=4, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            random_state=42, n_jobs=2, eval_metric="logloss"
        )
        xgbm.fit(X, y, sample_weight=weights)
        dump(xgbm, META_DIR / f"{_safe_key(symbol, timeframe)}__xgb.joblib")
        p_list, y_list = _cv_preds(xgbm, X, y, cv_splits, embargo)
        models_trained["xgb"] = True; cv_pl["xgb"] = p_list; cv_yl = y_list

    # Train LightGBM
    if "lgbm" in model_list:
        import lightgbm as lgb
        lgbm = lgb.LGBMClassifier(
            n_estimators=300, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
        trained_models["xgb"] = True
        cv_pl["xgb"] = p_list
        cv_yl = y_list

    # LightGBM
    if "lgbm" in available_models:
        import lightgbm as lgb
        lgbm = lgb.LGBMClassifier(
            n_estimators=300, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            random_state=42, n_jobs=2
        )
        lgbm.fit(X, y, sample_weight=weights)
        dump(lgbm, META_DIR / f"{_safe_key(symbol, timeframe)}__lgbm.joblib")
        p_list, y_list = _cv_preds(lgbm, X, y, cv_splits, embargo)
        models_trained["lgbm"] = True; cv_pl["lgbm"] = p_list; cv_yl = y_list

    if not models_trained:
        raise RuntimeError(f"no models trained for {symbol} {timeframe}")

    # per-model PF and ensemble
    model_cvpf: Dict[str, float] = {}
    for mname, p_list in cv_pl.items():
        model_cvpf[mname] = float(_purged_pf(p_list, cv_yl or [], 0.6))

        trained_models["lgbm"] = True
        cv_pl["lgbm"] = p_list
        cv_yl = y_list

    if not trained_models:
        return {"error": "no_models_trained", "symbol": symbol, "tf": timeframe}

    # Per-model CV PF
    model_cvpf: Dict[str, float] = {}
    for mname, p_list in cv_pl.items():
        model_cvpf[mname] = float(_purged_pf(p_list, cv_yl or [], thr))

    # Ensemble
    w, thr_ens, score_ens = _optuna_ensemble(cv_pl, cv_yl or [], base_thr=thr)

    # Upsert registry
    row = {
        "key": _safe_key(symbol, timeframe), "symbol": symbol, "tf": timeframe,
        "asset_class": asset_class, "features": want_cols,
        "entries": int(len(idx)), "trained_at": int(time.time()),
        "models": { m: {"file": f"{_safe_key(symbol, timeframe)}__{m}.joblib", "cv_pf": float(model_cvpf.get(m, 0.0))} for m in models_trained.keys() },
        "ens_weights": w, "threshold_ens": float(thr_ens), "cv_pf_score_ens": float(score_ens),
        "threshold": float(thr), "cv_pf_score": float(max(model_cvpf.values()) if model_cvpf else 0.0)
    }
    obj = {"models": []}
    if META_REG.exists():
        try: obj = json.loads(META_REG.read_text() or '{"models":[]}')
        except Exception: obj = {"models":[]}
    obj["models"] = [r for r in obj.get("models", []) if r.get("key") != row["key"]]
    obj["models"].append(row)
    tmp = META_REG.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2)); os.replace(tmp, META_REG)

    # return metrics used by orchestrator logs
    return {
        "entries": int(len(idx)),
        "models": list(models_trained.keys()),
        "model_cv_pf": model_cvpf,
        "ens_weights": w,
        "threshold_ens": float(thr_ens),
        "cv_pf_score_ens": float(score_ens),
    }
        "key": _safe_key(symbol, timeframe),
        "symbol": symbol,
        "tf": timeframe,
        "asset_class": asset_class,
        "features": want_cols,
        "entries": int(len(idx)),
        "trained_at": int(time.time()),
        "models": {
            m: {"file": f"{_safe_key(symbol, timeframe)}__{m}.joblib", "cv_pf": float(model_cvpf.get(m, 0.0))}
            for m in trained_models.keys()
        },
        "ens_weights": w,
        "threshold_ens": float(thr_ens),
        "cv_pf_score_ens": float(score_ens),
        "threshold": float(thr),
        "cv_pf_score": float(max(model_cvpf.values()) if model_cvpf else 0.0),
    }

    obj = {"models": []}
    if META_REG.exists():
        try:
            obj = json.loads(META_REG.read_text() or '{"models":[]}')
        except Exception:
            obj = {"models": []}
    obj["models"] = [r for r in obj.get("models", []) if r.get("key") != row["key"]]
    obj["models"].append(row)
    tmp = META_REG.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2))
    os.replace(tmp, META_REG)

    # Return metrics the orchestrator logs
    return {
        "ens_pf": float(score_ens),
        "threshold": float(thr_ens),
        "entries": int(len(idx)),
        "models": list(trained_models.keys()),
        "model_scores": model_cvpf,
    }

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python -m tools.meta_ensemble <symbol> <timeframe>")
        raise SystemExit(1)
    sym = sys.argv[1]
    tf = sys.argv[2]
    print(json.dumps(train_symbol_tf(sym, tf), indent=2))
