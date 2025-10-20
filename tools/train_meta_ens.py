#!/usr/bin/env python3
from __future__ import annotations
import os, json, time, warnings, re
from pathlib import Path
from typing import Dict, Any, List, Tuple
import numpy as np
import pandas as pd
from joblib import dump
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from tools.capital_session import capital_rest_login, capital_get_candles_df
from tools.symbol_resolver import read_symbols
from tools.consensus_engine import consensus_signal
from tools.ml.features import compute_features
from tools.ml.labels import label_meta_from_entries
from tools.ml.purged_cv import PurgedTimeSeriesSplit
from tools.ml.asset_class import resolve_asset_class
from tools.notifier import send_telegram, send_big

try:
    import optuna
except Exception:
    optuna = None

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state"; STATE.mkdir(parents=True, exist_ok=True)
META_DIR = STATE / "models_meta"; META_DIR.mkdir(parents=True, exist_ok=True)
META_REG = STATE / "models_meta.json"
PRO_REG  = STATE / "models_pro.json"

def _safe_key(symbol: str, tf: str) -> str:
    k = f"{symbol}__{tf}"
    return re.sub(r"[^A-Za-z0-9_.-]", "", k)

def _load_pro_config(symbol: str, tf: str) -> Dict[str, Any]:
    if not PRO_REG.exists(): return {}
    obj = json.loads(PRO_REG.read_text() or '{"models":[]}')
    rows = [r for r in obj.get("models", []) if r.get("symbol")==symbol and r.get("tf")==tf and r.get("strategy")=="CONSENSUS"]
    if not rows: return {}
    rows.sort(key=lambda r: int(r.get("trained_at", 0)), reverse=True)
    return rows[0].get("config") or {}

def _entry_points(df: pd.DataFrame, cfg: Dict[str, Any]) -> Tuple[np.ndarray, np.ndarray]:
    sig = consensus_signal(df, cfg); s = pd.Series(sig, index=df.index)
    prev = s.shift(1).fillna(0); buy = (prev <= 0) & (s > 0); sell = (prev >= 0) & (s < 0)
    idx = np.where((buy | sell).values)[0]; dirs = np.where(buy.values[idx], 1, -1)
    return idx, dirs

def _purged_pf(p_list: List[np.ndarray], y_list: List[np.ndarray], thr: float) -> float:
    TP, FP = 0, 0
    for p,y in zip(p_list,y_list):
        yhat = (p >= thr).astype(int)
        TP += int(((yhat==1)&(y==1)).sum()); FP += int(((yhat==1)&(y==0)).sum())
    return TP / (FP + 1.0)

def _features_for_class(asset_class: str) -> List[str]:
    ac = asset_class
    if ac == "crypto":
        return ["sma_diff","ema_diff","rsi14","macd_hist","atr14","obv"]
    if ac == "index":
        return ["ema_diff","rsi14","adx14","vola50","atr14"]
    if ac == "stock":
        return ["ema_diff","rsi14","stoch_k","obv","atr14"]
    if ac in ("metal","energy","fx"):
        return ["ema_diff","rsi14","atr14","vola50","rng_pct"]
    return ["ema_diff","rsi14","vola50","rng_pct"]

def _cv_preds(model, X: pd.DataFrame, y: np.ndarray, splits: int, embargo: int) -> Tuple[List[np.ndarray], List[np.ndarray]]:
    cv = PurgedTimeSeriesSplit(n_splits=splits, embargo=embargo)
    idx = np.arange(len(X)); p_list: List[np.ndarray] = []; y_list: List[np.ndarray] = []
    for tr, te in cv.split(idx):
        if len(np.unique(y[tr]))<2 or len(np.unique(y[te]))<2: continue
        m = model.__class__(**getattr(model, "get_params", lambda: {})())
        if hasattr(m, "random_state"):
            try: m.random_state = 42
            except Exception: pass
        m.fit(X.iloc[tr], y[tr])
        try:
            p = m.predict_proba(X.iloc[te])[:,1]
        except Exception:
            p = m.predict(X.iloc[te]).astype(float); p = np.clip(p, 0.0, 1.0)
        p_list.append(p.astype(float)); y_list.append(y[te].astype(int))
    return p_list, y_list

def _optuna_ensemble(pdict: Dict[str, List[np.ndarray]], y_list: List[np.ndarray], base_thr: float = 0.6) -> Tuple[Dict[str,float], float, float]:
    names = sorted(pdict.keys()); k = len(names)
    if not optuna:
        w = {n: 1.0/k for n in names}
        p_ens = [sum(w[n]*pdict[n][i] for n in names) for i in range(len(y_list))]
        return w, base_thr, float(_purged_pf(p_ens, y_list, base_thr))
    def make_ens(wv: List[float]) -> List[np.ndarray]:
        s = sum(wv) + 1e-9; wn = [x/s for x in wv]
        return [sum(wn[j]*pdict[names[j]][i] for j in range(k)) for i in range(len(y_list))]
    study = optuna.create_study(direction="maximize", study_name="meta_ensemble")
    def objective(trial: "optuna.Trial") -> float:
        ws = [trial.suggest_float(f"w_{n}", 0.0, 1.0) for n in names]
        thr = trial.suggest_float("thr", 0.50, 0.80, step=0.02)
        p_ens = make_ens(ws); return float(_purged_pf(p_ens, y_list, thr))
    study.optimize(objective, n_trials=int(os.getenv("ENS_TUNER_TRIALS","60")), show_progress_bar=False)
    best = study.best_params
    ws = [best.get(f"w_{n}", 1.0) for n in names]; s = sum(ws) + 1e-9; wn = [x/s for x in ws]
    w = {names[j]: float(wn[j]) for j in range(k)}
    thr = float(best.get("thr", base_thr))
    p_ens = [sum(w[n]*pdict[n][i] for n in names) for i in range(len(y_list))]
    score = float(_purged_pf(p_ens, y_list, thr))
    return w, thr, score

def main():
    capital_rest_login()
    symbols = read_symbols()
    tfs = [s.strip() for s in (os.getenv("TRAIN_TFS") or "15m,1h,4h").split(",") if s.strip()]
    max_total = int(os.getenv("TRAIN_MAX_TOTAL", "10000"))
    page_size = int(os.getenv("TRAIN_PAGE_SIZE", "200"))
    sleep_sec = float(os.getenv("TRAIN_PAGE_SLEEP", "1.5"))
    pt_mult = float(os.getenv("TB_PT_MULT", "2.0"))
    sl_mult = float(os.getenv("TB_SL_MULT", "2.0"))
    max_hold = int(os.getenv("TB_MAX_HOLD", "48"))
    cv_splits = int(os.getenv("META_CV_SPLITS", "5"))
    embargo = int(os.getenv("META_EMBARGO", str(max_hold)))
    decay = float(os.getenv("TIME_DECAY", "0.995"))
    model_list = [m.strip() for m in (os.getenv("META_MODELS","gbdt,xgb,lgbm,lr")).split(",") if m.strip()]

    # Tilanneviesti
    send_telegram(f"🚀 META-ensemble start symbols={len(symbols)} tfs={','.join(tfs)} models={','.join(model_list)}")

    # Saatavuudet
    if "xgb" in model_list:
        try: import xgboost as xgb  # noqa
        except Exception: model_list = [m for m in model_list if m!="xgb"]
    if "lgbm" in model_list:
        try: import lightgbm as lgb  # noqa
        except Exception: model_list = [m for m in model_list if m!="lgbm"]

    ok_lines: List[str] = []
    for sym in symbols:
        for tf in tfs:
            try:
                cfg = _load_pro_config(sym, tf)
                if not cfg: 
                    print(f"[SKIP] no base config for {sym} {tf}", flush=True); 
                    continue
                df = capital_get_candles_df(sym, tf, total_limit=max_total, page_size=page_size, sleep_sec=sleep_sec)
                if df.empty or len(df) < 600: 
                    print(f"[WARN] insufficient data {sym} {tf} ({len(df)})", flush=True); 
                    continue

                feats_all = compute_features(df).replace([np.inf,-np.inf], np.nan).ffill().bfill().fillna(0.0)
                idx, dirs = _entry_points(df, cfg)
                if len(idx) < 50: 
                    print(f"[WARN] too few entries {sym} {tf} ({len(idx)})", flush=True); 
                    continue

                asset_class = resolve_asset_class(sym)
                want_cols = _features_for_class(asset_class)
                X = feats_all.iloc[idx].reindex(columns=want_cols).fillna(0.0)
                y,_ = label_meta_from_entries(df, idx, dirs, pt_mult=pt_mult, sl_mult=sl_mult, max_holding=max_hold)

                # painotus
                n = len(X); weights = (decay ** (np.arange(n)[::-1])).astype(float)

                models: Dict[str, Any] = {}
                cv_pl: Dict[str, List[np.ndarray]] = {}
                cv_yl: List[np.ndarray] = None

                # GBDT
                if "gbdt" in model_list:
                    gbdt = GradientBoostingClassifier(random_state=42)
                    gbdt.fit(X, y, sample_weight=weights)
                    dump(gbdt, META_DIR / f"{_safe_key(sym, tf)}__gbdt.joblib")
                    p_list, y_list = _cv_preds(gbdt, X, y, cv_splits, embargo)
                    models["gbdt"] = True; cv_pl["gbdt"] = p_list; cv_yl = y_list

                # Logistic Regression
                if "lr" in model_list:
                    lr = LogisticRegression(max_iter=200)
                    lr.fit(X, y, sample_weight=weights)
                    dump(lr, META_DIR / f"{_safe_key(sym, tf)}__lr.joblib")
                    p_list, y_list = _cv_preds(lr, X, y, cv_splits, embargo)
                    models["lr"] = True; cv_pl["lr"] = p_list; cv_yl = y_list

                # XGBoost
                if "xgb" in model_list:
                    import xgboost as xgb
                    xgbm = xgb.XGBClassifier(
                        n_estimators=200, max_depth=4, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                        random_state=42, n_jobs=2, eval_metric="logloss"
                    )
                    xgbm.fit(X, y, sample_weight=weights)
                    dump(xgbm, META_DIR / f"{_safe_key(sym, tf)}__xgb.joblib")
                    p_list, y_list = _cv_preds(xgbm, X, y, cv_splits, embargo)
                    models["xgb"] = True; cv_pl["xgb"] = p_list; cv_yl = y_list

                # LightGBM
                if "lgbm" in model_list:
                    import lightgbm as lgb
                    lgbm = lgb.LGBMClassifier(
                        n_estimators=300, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                        random_state=42, n_jobs=2
                    )
                    lgbm.fit(X, y, sample_weight=weights)
                    dump(lgbm, META_DIR / f"{_safe_key(sym, tf)}__lgbm.joblib")
                    p_list, y_list = _cv_preds(lgbm, X, y, cv_splits, embargo)
                    models["lgbm"] = True; cv_pl["lgbm"] = p_list; cv_yl = y_list

                if not models:
                    print(f"[SKIP] no models trained for {sym} {tf}", flush=True); 
                    continue

                # per-malli PF + ensemble
                model_cvpf: Dict[str, float] = {}
                for mname, p_list in cv_pl.items():
                    model_cvpf[mname] = float(_purged_pf(p_list, cv_yl, 0.6))

                w, thr_ens, score_ens = _optuna_ensemble(cv_pl, cv_yl, base_thr=0.6)

                # rekisteri upsert
                row = {
                    "key": _safe_key(sym, tf), "symbol": sym, "tf": tf,
                    "asset_class": asset_class, "features": want_cols,
                    "entries": int(len(idx)), "trained_at": int(time.time()),
                    "models": { m: {"file": f"{_safe_key(sym, tf)}__{m}.joblib", "cv_pf": float(model_cvpf.get(m, 0.0))} for m in models.keys() },
                    "ens_weights": w, "threshold_ens": float(thr_ens), "cv_pf_score_ens": float(score_ens),
                    "threshold": 0.60, "cv_pf_score": float(max(model_cvpf.values()) if model_cvpf else 0.0)
                }
                obj = {"models": []}
                if META_REG.exists():
                    try: obj = json.loads(META_REG.read_text() or '{"models":[]}')
                    except Exception: obj = {"models":[]}
                obj["models"] = [r for r in obj.get("models", []) if r.get("key") != row["key"]]
                obj["models"].append(row)
                tmp = META_REG.with_suffix(".tmp")
                tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2)); os.replace(tmp, META_REG)

                # Telegram rivi
                msg = f"{sym} {tf} ens_pf={score_ens:.3f} thr={thr_ens:.2f} entries={len(idx)} models={','.join(models.keys())}"
                send_telegram(f"✅ [META ENS OK] {msg}")
                ok_lines.append(f"✅ {msg}")
                print(f"[OK][ENS] {msg}", flush=True)
                time.sleep(0.2)
            except Exception as e:
                print(f"[ERROR][ENS] {sym} {tf}: {e}", flush=True)

    send_big("📣 META-ensemble koulutus valmis", ok_lines, max_lines=200)
    print(f"[DONE][ENS] updated -> {META_REG}", flush=True)

if __name__ == "__main__":
    main()
