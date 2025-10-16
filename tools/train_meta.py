from __future__ import annotations
import os, json, time, warnings, re
from pathlib import Path
from typing import Dict, Any, List, Tuple
import numpy as np
import pandas as pd
from joblib import dump
from sklearn.metrics import roc_auc_score
from sklearn.ensemble import GradientBoostingClassifier
from tools.capital_session import capital_rest_login, capital_get_candles_df
from tools.symbol_resolver import read_symbols
from tools.consensus_engine import consensus_signal
from tools.ml.features import compute_features
from tools.ml.labels import label_meta_from_entries
from tools.ml.purged_cv import PurgedTimeSeriesSplit

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
    obj = json.loads(PRO_REG.read_text())
    rows = [r for r in obj.get("models", []) if r.get("symbol")==symbol and r.get("tf")==tf and r.get("strategy")=="CONSENSUS"]
    if not rows: return {}
    rows.sort(key=lambda r: int(r.get("trained_at", 0)), reverse=True)
    return rows[0].get("config") or {}

def _entry_points(df: pd.DataFrame, cfg: Dict[str, Any]) -> Tuple[np.ndarray, np.ndarray]:
    sig = consensus_signal(df, cfg); s = pd.Series(sig, index=df.index)
    prev = s.shift(1).fillna(0); buy = (prev <= 0) & (s > 0); sell = (prev >= 0) & (s < 0)
    idx = np.where((buy | sell).values)[0]; dirs = np.where(buy.values[idx], 1, -1)
    return idx, dirs

def _purged_auc(X: pd.DataFrame, y: np.ndarray, n_splits: int, embargo: int) -> float:
    aucs = []; cv = PurgedTimeSeriesSplit(n_splits=n_splits, embargo=embargo)
    id_all = np.arange(len(X))
    for tr, te in cv.split(id_all):
        if len(np.unique(y[tr]))<2 or len(np.unique(y[te]))<2: continue
        clf = GradientBoostingClassifier(random_state=42)
        clf.fit(X.iloc[tr], y[tr]); p = clf.predict_proba(X.iloc[te])[:,1]
        aucs.append(roc_auc_score(y[te], p))
    return float(np.mean(aucs)) if aucs else 0.5

def _best_threshold(y_true: np.ndarray, p: np.ndarray) -> float:
    grid = [0.5, 0.55, 0.6, 0.65, 0.7]; best, best_thr = -1e9, 0.6
    for thr in grid:
        yhat = (p >= thr).astype(int)
        tp = int(((yhat==1)&(y_true==1)).sum()); fp = int(((yhat==1)&(y_true==0)).sum())
        score = tp - 0.5*fp
        if score > best: best = score; best_thr = thr
    return best_thr

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
    registry: List[Dict[str, Any]] = []
    print(f"[META-TRAIN] start symbols={len(symbols)} tfs={tfs} pt={pt_mult} sl={sl_mult} hold={max_hold} cv={cv_splits} embargo={embargo}", flush=True)
    for sym in symbols:
        for tf in tfs:
            try:
                cfg = _load_pro_config(sym, tf)
                if not cfg: print(f"[SKIP] no base config for {sym} {tf}", flush=True); continue
                df = capital_get_candles_df(sym, tf, total_limit=max_total, page_size=page_size, sleep_sec=sleep_sec)
                if df.empty or len(df) < 600: print(f"[WARN] insufficient data {sym} {tf} ({len(df)})", flush=True); continue
                feats = compute_features(df)
                idx, dirs = _entry_points(df, cfg)
                if len(idx) < 50: print(f"[WARN] too few entries {sym} {tf} ({len(idx)})", flush=True); continue
                y,_ = label_meta_from_entries(df, idx, dirs, pt_mult=pt_mult, sl_mult=sl_mult, max_holding=max_hold)
                X = feats.iloc[idx].replace([np.inf,-np.inf], np.nan).fillna(method="ffill").fillna(method="bfill").fillna(0.0)
                auc = _purged_auc(X, y, n_splits=cv_splits, embargo=embargo)
                clf = GradientBoostingClassifier(random_state=42); clf.fit(X, y); p = clf.predict_proba(X)[:,1]
                thr = _best_threshold(y, p)
                key = _safe_key(sym, tf)
                outp = META_DIR / f"{key}.joblib"; dump(clf, outp)
                row = {"key": key, "symbol": sym, "tf": tf, "threshold": float(thr),
                       "auc_purged": float(auc), "pt_mult": pt_mult, "sl_mult": sl_mult,
                       "max_hold": max_hold, "trained_at": int(time.time()),
                       "features": list(X.columns), "entries": int(len(idx)), "class_balance": float(y.mean())}
                registry.append(row)
                print(f"[OK][META] {sym} {tf} -> AUC={auc:.3f} thr={thr:.2f} entries={len(idx)} pos_rate={y.mean():.2f}", flush=True)
                time.sleep(0.2)
            except Exception as e:
                print(f"[ERROR][META] {sym} {tf}: {e}", flush=True)
    tmp = META_REG.with_suffix(".tmp"); open(tmp,"w").write(json.dumps({"models": registry}, ensure_ascii=False, indent=2)); os.replace(tmp, META_REG)
    print(f"[DONE][META] saved -> {META_REG} count={len(registry)}", flush=True)

if __name__ == "__main__":
    main()
