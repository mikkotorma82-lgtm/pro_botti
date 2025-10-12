from __future__ import annotations
import os, sys, json
from pathlib import Path
import numpy as np
import pandas as pd
from joblib import load

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def _fallback_load_history(data_dir: Path, symbol: str, tf: str) -> pd.DataFrame:
    for name in (f"{symbol}_{tf}.csv", f"{symbol}-{tf}.csv", f"{symbol}{tf}.csv"):
        p = data_dir / name
        if p.exists():
            try:
                return pd.read_csv(p)
            except Exception:
                pass
    return pd.DataFrame()

try:
    from core.io import load_history as _project_load_history  # type: ignore
    def load_history(data_dir: Path, symbol: str, tf: str) -> pd.DataFrame:
        return _project_load_history(data_dir, symbol, tf)
except Exception:
    def load_history(data_dir: Path, symbol: str, tf: str) -> pd.DataFrame:
        return _fallback_load_history(data_dir, symbol, tf)

DATA_DIR   = Path(os.getenv("DATA_DIR",   "data"))
MODELS_DIR = Path(os.getenv("MODELS_DIR", "models"))

def safe_features(df: pd.DataFrame) -> np.ndarray:
    if df is None or len(df) == 0:
        return np.zeros((1, 1), dtype=float)
    cols = [c for c in df.columns if str(c).lower() in ("close","close_price","price","last","c")]
    if not cols:
        return np.zeros((len(df), 1), dtype=float)
    s = pd.to_numeric(df[cols[0]], errors="coerce").fillna(method="ffill").fillna(method="bfill")
    ret1 = s.pct_change(1).fillna(0.0).to_numpy()
    ret3 = s.pct_change(3).fillna(0.0).to_numpy()
    ret5 = s.pct_change(5).fillna(0.0).to_numpy()
    X = np.column_stack([ret1, ret3, ret5])
    X = np.nan_to_num(X, copy=False)
    return X

def _model_expected_n_features(clf) -> int | None:
    # yritetään löytää n_features_in_ Pipeline-stepiltä (esim. StandardScaler) tai estimatorilta
    n_list = []
    steps = getattr(clf, "steps", None)
    if steps:
        for _, obj in steps:
            n = getattr(obj, "n_features_in_", None)
            if isinstance(n, (int, np.integer)):
                n_list.append(int(n))
    n = getattr(clf, "n_features_in_", None)
    if isinstance(n, (int, np.integer)):
        n_list.append(int(n))
    return max(n_list) if n_list else None

def pad_or_truncate(X: np.ndarray, n_target: int) -> np.ndarray:
    if X.ndim == 1:
        X = X.reshape(-1, 1)
    n_cur = X.shape[1]
    if n_cur == n_target:
        return X
    if n_cur > n_target:
        return X[:, -n_target:]
    out = np.zeros((X.shape[0], n_target), dtype=float)
    out[:, :n_cur] = X
    return out

def decide_side(clf, X_row: np.ndarray) -> str:
    try:
        y = clf.predict(X_row.reshape(1, -1))
        return "BUY" if int(y[0]) == 1 else "SELL"
    except Exception as e:
        print(f"[WARN] model predict failed: {e}; fallback SELL", file=sys.stderr)
        return "SELL"

def run_one(symbol: str, tf: str) -> None:
    df = load_history(DATA_DIR, symbol, tf)
    model_path = MODELS_DIR / f"pro_{symbol}_{tf}.joblib"
    if not model_path.exists():
        print(f"[WARN] model missing: {model_path}", file=sys.stderr)
        return
    try:
        clf = load(model_path)
    except Exception as e:
        print(f"[WARN] model load failed ({symbol} {tf}): {e}", file=sys.stderr)
        return

    X = safe_features(df)
    n_target = _model_expected_n_features(clf)
    if isinstance(n_target, int) and n_target > 0:
        X = pad_or_truncate(X, n_target)

    side = decide_side(clf, X[-1])
    print(json.dumps({"symbol": symbol, "tf": tf, "side": side}, ensure_ascii=False))

def main() -> None:
    symbols = [x.strip().upper() for x in os.getenv("SYMBOLS", "BTCUSD,ETHUSD").split(",") if x.strip()]
    tfs     = [x.strip()          for x in os.getenv("TFS", "15m,1h,4h").split(",")          if x.strip()]
    for s in symbols:
        for tf in tfs:
            try:
                run_one(s, tf)
            except Exception as e:
                print(f"[ERROR] {s} {tf}: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
