from __future__ import annotations
import os, json, time, warnings, re
from pathlib import Path
from typing import Dict, Any, List, Tuple
import numpy as np
import pandas as pd
from joblib import load
import optuna
from tools.capital_session import capital_rest_login, capital_get_candles_df
from tools.symbol_resolver import read_symbols
from tools.consensus_engine import consensus_signal
from tools.ml.features import compute_features
from tools.ml.labels import label_meta_from_entries
from tools.ml.purged_cv import PurgedTimeSeriesSplit

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state"; STATE.mkdir(parents=True, exist_ok=True)
META_DIR = STATE / "models_meta"
META_REG = STATE / "models_meta.json"
PRO_REG  = STATE / "models_pro.json"

def _safe_key(symbol: str, tf: str) -> str:
    k = f"{symbol}__{tf}"
    return re.sub(r"[^A-Za-z0-9_.-]", "", k)

def _load_pro_config(symbol: str, tf: str) -> Dict[str, Any]:
    if not PRO_REG.exists(): return {}
    obj = json.loads(PRO_REG.read_text())
    rows = [r for r in obj.get("models", []) if r.get("symbol")==symbol and r.get("tf")==tf and r.get("strategy")=="CONSENSUS"]
    if not rows: return {}
    rows.sort(key=lambda r: int(r.get("trained_at", 0)), reverse=True)
    return rows[0].get("config") or {}

def _load_meta_model(symbol: str, tf: str):
    key = _safe_key(symbol, tf)
    path = META_DIR / f"{key}.joblib"
    if not path.exists(): return None
    try: return load(path)
    except Exception: return None

def _load_meta_row(symbol: str, tf: str) -> Dict[str, Any] | None:
    if not META_REG.exists(): return None
    try:
        obj = json.loads(META_REG.read_text())
        key = _safe_key(symbol, tf)
        for r in obj.get("models", []):
            if r.get("key") == key:
                return r
    except Exception:
        pass
    return None

def _entry_points(df: pd.DataFrame, cfg: Dict[str, Any]) -> Tuple[np.ndarray, np.ndarray]:
    sig = consensus_signal(df, cfg); s = pd.Series(sig, index=df.index)
    prev = s.shift(1).fillna(0); buy=(prev<=0)&(s>0); sell=(prev>=0)&(s<0)
    idx = np.where((buy|sell).values)[0]; dirs = np.where(buy.values[idx], 1, -1)
    return idx, dirs

def _tp_fp_at_threshold(y_true: np.ndarray, p: np.ndarray, thr: float) -> Tuple[int,int]:
    yhat = (p >= thr).astype(int); tp = int(((yhat==1) & (y_true==1)).sum()); fp = int(((yhat==1) & (y_true==0)).sum())
    return tp, fp

def _purged_score(p_list: List[np.ndarray], y_list: List[np.ndarray], thr: float) -> float:
    TP, FP = 0, 0
    for p, y in zip(p_list, y_list):
        tp, fp = _tp_fp_at_threshold(y, p, thr); TP += tp; FP += fp
    return TP / (FP + 1.0)

def tune_one(symbol: str, tf: str, df: pd.DataFrame, cfg: Dict[str, Any]) -> Dict[str, Any]:
    model = _load_meta_model(symbol, tf)
    row = _load_meta_row(symbol, tf)
    if model is None or row is None:
        return {"ok": False, "reason": "no_meta_model_or_row"}

    exp_cols = row.get("features", [])
    if not exp_cols:
        return {"ok": False, "reason": "no_feature_list_saved"}

    feats_all = compute_features(df).replace([np.inf,-np.inf], np.nan).ffill().bfill().fillna(0.0)
    idx, dirs = _entry_points(df, cfg)
    if len(idx) < 50:
        return {"ok": False, "reason": "too_few_entries", "entries": int(len(idx))}

    def build_cv_preds(pt_mult: float, sl_mult: float, max_hold: int) -> Tuple[List[np.ndarray], List[np.ndarray]]:
        y,_ = label_meta_from_entries(df, idx, dirs, pt_mult=pt_mult, sl_mult=sl_mult, max_holding=max_hold)
        # Täsmälleen samat sarakkeet ja järjestys kuin mallissa
        X = feats_all.iloc[idx].reindex(columns=exp_cols).fillna(0.0)
        cv = PurgedTimeSeriesSplit(n_splits=int(os.getenv("META_CV_SPLITS","5")), embargo=int(os.getenv("META_EMBARGO","48")))
        ids = np.arange(len(X)); p_list, y_list = [], []
        for tr, te in cv.split(ids):
            p = model.predict_proba(X.iloc[te])[:,1]
            p_list.append(p.astype(float)); y_list.append(y[te].astype(int))
        return p_list, y_list

    study = optuna.create_study(direction="maximize", study_name=f"meta_thr_tb__{_safe_key(symbol, tf)}")
    def objective(trial: optuna.Trial) -> float:
        pt  = trial.suggest_float("pt_mult", 1.0, 4.0, step=0.5)
        sl  = trial.suggest_float("sl_mult", 1.0, 4.0, step=0.5)
        hold= trial.suggest_int("max_hold", 12, 96, step=6)
        thr = trial.suggest_float("thr", 0.50, 0.80, step=0.02)
        p_list, y_list = build_cv_preds(pt, sl, hold)
        if not p_list: return 0.0
        score = _purged_score(p_list, y_list, thr)
        score -= 0.0005 * (hold - 48)
        return float(score)

    n_trials = int(os.getenv("TUNER_TRIALS","60"))
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    best = study.best_params; best_score = float(study.best_value)

    # Päivitä rekisteri
    try:
        obj = json.loads(META_REG.read_text()) if META_REG.exists() else {"models":[]}
        key = _safe_key(symbol, tf)
        updated = False
        for r in obj.get("models", []):
            if r.get("key") == key:
                r.update({
                    "threshold": round(best["thr"],3),
                    "pt_mult": round(best["pt_mult"],2),
                    "sl_mult": round(best["sl_mult"],2),
                    "max_hold": int(best["max_hold"]),
                    "tuned_at": int(time.time()),
                    "tuner_trials": n_trials,
                    "tuner_score": best_score
                })
                updated = True
                break
        if not updated:
            obj["models"].append({
                "key": key, "symbol": symbol, "tf": tf,
                "threshold": round(best["thr"],3),
                "pt_mult": round(best["pt_mult"],2),
                "sl_mult": round(best["sl_mult"],2),
                "max_hold": int(best["max_hold"]),
                "tuned_at": int(time.time()),
                "tuner_trials": n_trials,
                "tuner_score": best_score,
                "features": exp_cols
            })
        tmp = META_REG.with_suffix(".tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2)); os.replace(tmp, META_REG)
    except Exception:
        pass

    return {"ok": True, "best": best, "score": best_score}

def main():
    capital_rest_login()
    symbols = read_symbols()  # -> config/symbols.txt
    tfs = [s.strip() for s in (os.getenv("TRAIN_TFS") or "15m,1h,4h").split(",") if s.strip()]
    max_total = int(os.getenv("TRAIN_MAX_TOTAL","10000"))
    page_size = int(os.getenv("TRAIN_PAGE_SIZE","200"))
    sleep_sec = float(os.getenv("TRAIN_PAGE_SLEEP","1.5"))
    print(f"[TUNER] start symbols={len(symbols)} tfs={tfs} trials={os.getenv('TUNER_TRIALS','60')}", flush=True)
    for sym in symbols:
        for tf in tfs:
            try:
                cfg = _load_pro_config(sym, tf)
                if not cfg: print(f"[TUNER][SKIP] no base config for {sym} {tf}", flush=True); continue
                df = capital_get_candles_df(sym, tf, total_limit=max_total, page_size=page_size, sleep_sec=sleep_sec)
                if df.empty or len(df) < 600: print(f"[TUNER][SKIP] insufficient data {sym} {tf}", flush=True); continue
                res = tune_one(sym, tf, df, cfg); print(f"[TUNER] {sym} {tf} -> {res}", flush=True)
            except Exception as e:
                print(f"[TUNER][ERROR] {sym} {tf}: {e}", flush=True)
    print("[TUNER] done", flush=True)

if __name__ == "__main__":
    main()
