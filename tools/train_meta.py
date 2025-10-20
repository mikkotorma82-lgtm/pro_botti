from __future__ import annotations
import os, json, time, warnings, re
from pathlib import Path
from typing import Dict, Any, List, Tuple
import numpy as np
import pandas as pd
from joblib import dump
from sklearn.ensemble import GradientBoostingClassifier
from tools.capital_session import capital_rest_login, capital_get_candles_df
from tools.symbol_resolver import read_symbols
from tools.consensus_engine import consensus_signal
from tools.ml.features import compute_features
from tools.ml.labels import label_meta_from_entries
from tools.ml.purged_cv import PurgedTimeSeriesSplit
from tools.ml.asset_class import resolve_asset_class
from tools.notifier import send_telegram, send_big  # UUSI

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

def _pf_proxy(y_true: np.ndarray, p: np.ndarray, thr: float) -> float:
    yhat = (p >= thr).astype(int)
    tp = int(((yhat==1) & (y_true==1)).sum())
    fp = int(((yhat==1) & (y_true==0)).sum())
    return tp / (fp + 1.0)

def _cv_choose_threshold(X: pd.DataFrame, y: np.ndarray, splits: int, embargo: int) -> Tuple[float, float]:
    cv = PurgedTimeSeriesSplit(n_splits=splits, embargo=embargo)
    idx = np.arange(len(X))
    probs, truths = [], []
    for tr, te in cv.split(idx):
        if len(np.unique(y[tr])) < 2 or len(np.unique(y[te])) < 2:
            continue
        from sklearn.ensemble import GradientBoostingClassifier
        clf = GradientBoostingClassifier(random_state=42)
        clf.fit(X.iloc[tr], y[tr])
        p = clf.predict_proba(X.iloc[te])[:,1]
        p = np.clip(p, 0.02, 0.98)
        probs.append(p.astype(float)); truths.append(y[te].astype(int))
    if not probs:
        return 0.6, 0.0
    grid = np.arange(0.50, 0.81, 0.02)
    best_thr, best_score = 0.6, -1.0
    for thr in grid:
        score = sum(_pf_proxy(t, p, thr) for p,t in zip(probs,truths)) / len(probs)
        if score > best_score:
            best_score, best_thr = float(score), float(thr)
    return best_thr, best_score

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

    registry: List[Dict[str, Any]] = []
    print(f"[META-TRAIN] start symbols={len(symbols)} tfs={tfs} pt={pt_mult} sl={sl_mult} hold={max_hold} cv={cv_splits} embargo={embargo}", flush=True)

    ok_lines: List[str] = []  # Telegram-yhteenveto

    for sym in symbols:
        for tf in tfs:
            try:
                cfg = _load_pro_config(sym, tf)
                if not cfg:
                    print(f"[SKIP] no base config for {sym} {tf}", flush=True); continue
                df = capital_get_candles_df(sym, tf, total_limit=max_total, page_size=page_size, sleep_sec=sleep_sec)
                if df.empty or len(df) < 600:
                    print(f"[WARN] insufficient data {sym} {tf} ({len(df)})", flush=True); continue

                feats_all = compute_features(df)
                idx, dirs = _entry_points(df, cfg)
                if len(idx) < 50:
                    print(f"[WARN] too few entries {sym} {tf} ({len(idx)})", flush=True); continue

                asset_class = resolve_asset_class(sym)
                want_cols = _features_for_class(asset_class)
                feats_all = feats_all.replace([np.inf,-np.inf], np.nan).fillna(method="ffill").fillna(method="bfill")
                feats_all = feats_all.fillna(0.0)
                X = feats_all.iloc[idx]
                X = X.reindex(columns=want_cols).fillna(0.0)

                y,_ = label_meta_from_entries(df, idx, dirs, pt_mult=pt_mult, sl_mult=sl_mult, max_holding=max_hold)
                thr, cv_score = _cv_choose_threshold(X, y, splits=cv_splits, embargo=embargo)

                n = len(X)
                weights = (decay ** (np.arange(n)[::-1])).astype(float)
                clf = GradientBoostingClassifier(random_state=42)
                clf.fit(X, y, sample_weight=weights)

                key = _safe_key(sym, tf)
                dump(clf, META_DIR / f"{key}.joblib")
                row = {"key": key, "symbol": sym, "tf": tf,
                       "threshold": float(thr), "cv_pf_score": float(cv_score),
                       "pt_mult": pt_mult, "sl_mult": sl_mult, "max_hold": max_hold,
                       "trained_at": int(time.time()), "asset_class": asset_class,
                       "features": list(X.columns), "entries": int(len(idx)),
                       "class_balance": float(y.mean())}
                registry.append(row)
                msg_line = f"{sym} {tf} thr={thr:.2f} cv_pf={cv_score:.3f} entries={len(idx)}"
                ok_lines.append(f"✅ {msg_line}")
                send_telegram(f"✅ [META OK] {msg_line}")
                print(f"[OK][META] {msg_line}", flush=True)
                time.sleep(0.2)
            except Exception as e:
                print(f"[ERROR][META] {sym} {tf}: {e}", flush=True)

    tmp = META_REG.with_suffix(".tmp")
    open(tmp,"w").write(json.dumps({"models": registry}, ensure_ascii=False, indent=2))
    os.replace(tmp, META_REG)
    send_big("📣 META-koulutus valmis", ok_lines, max_lines=120)
    send_telegram(f"📦 Tallennettu -> {META_REG} count={len(registry)}")

    print(f"[DONE][META] saved -> {META_REG} count={len(registry)}", flush=True)

if __name__ == "__main__":
    main()
