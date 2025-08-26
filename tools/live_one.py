from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np, pandas as pd
from joblib import load
from core.io import load_history

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "history"
MODEL_DIR = ROOT / "models"
DEFAULT_FEATS = [
    "ret1",
    "ret5",
    "vol5",
    "ema12",
    "ema26",
    "macd",
    "rsi14",
    "atr14",
    "ema_gap",
]


def to_ts_iso(v):
    t = pd.to_datetime(v, utc=True)
    return int(t.timestamp()), t.isoformat()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--tf", required=True)
    ap.add_argument("--limit_rows", type=int, default=2000)
    args = ap.parse_args()

    symbol, tf = args.symbol, args.tf
    df = load_history(DATA_DIR, symbol, tf)
    if args.limit_rows and len(df) > args.limit_rows:
        df = df.tail(args.limit_rows)

    model_path = MODEL_DIR / f"pro_{symbol}_{tf}.joblib"
    clf = load(model_path)

    feats = list(getattr(clf, "feature_names_", DEFAULT_FEATS))
    feats = [f for f in feats if f in df.columns]
    if not feats:
        raise ValueError(f"No usable features in data for {symbol} {tf}")

    X = df[feats].tail(1).to_numpy()
    probs = clf.predict_proba(X)[0]
    classes = [int(c) for c in getattr(clf, "classes_", np.arange(len(probs)))]
    proba_map = {str(int(c)): float(p) for c, p in zip(classes, probs)}
    signal = int(classes[int(np.argmax(probs))])

    ts, iso = to_ts_iso(df["time"].iloc[-1])

    out = {
        "symbol": symbol,
        "tf": tf,
        "time": ts,
        "time_iso": iso,
        "price": float(df["close"].iloc[-1]),
        "signal": signal,
        "proba": proba_map,
        "features_used": feats,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
