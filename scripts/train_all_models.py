#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, time
from pathlib import Path
from typing import List
import numpy as np, pandas as pd
from joblib import dump
from sklearn.ensemble import RandomForestClassifier
from tools.data_sources import fetch_ohlcv

ROOT   = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
MODELS.mkdir(parents=True, exist_ok=True)

FEATS = ["ret1","ret5","vol5","ema12","ema26","macd","rsi14","atr14","ema_gap"]

def env_list(name: str, default_csv: str) -> List[str]:
    v = os.getenv(name, default_csv)
    return [s.strip() for s in v.split(",") if s.strip()]

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    z = df.copy()
    c = pd.to_numeric(z["close"], errors="coerce")
    z["ret1"]  = c.pct_change()
    z["ret5"]  = c.pct_change(5)
    z["vol5"]  = z["ret1"].rolling(5).std().fillna(0.0)
    z["ema12"] = c.ewm(span=12, adjust=False).mean()
    z["ema26"] = c.ewm(span=26, adjust=False).mean()
    z["macd"]  = z["ema12"] - z["ema26"]
    diff = c.diff()
    up = diff.clip(lower=0).rolling(14).mean()
    dn = (-diff.clip(upper=0)).rolling(14).mean()
    rs = up / dn.replace(0, np.nan)
    z["rsi14"] = 100 - (100 / (1 + rs))
    if {"high","low","close"}.issubset(z.columns):
        tr = np.maximum(
            z["high"] - z["low"],
            np.maximum((z["high"] - z["close"].shift()).abs(), (z["low"] - z["close"].shift()).abs()),
        )
        z["atr14"] = tr.rolling(14).mean()
    else:
        z["atr14"] = 0.0
    z["ema_gap"] = (c - z["ema12"]) / z["ema12"]
    z = z.replace([np.inf,-np.inf], np.nan).dropna()
    return z

def label_next_up(df: pd.DataFrame) -> pd.Series:
    ret1_fwd = pd.to_numeric(df["close"], errors="coerce").pct_change().shift(-1)
    return (ret1_fwd > 0).astype(int).iloc[:-1]

def train_one(sym: str, tf: str, lookback_days: int):
    df = fetch_ohlcv(sym, tf, lookback_days)
    if df is None or df.empty or len(df) < 200:
        print(f"[train][skip] no/low data {sym} {tf}")
        return
    feats = build_features(df).iloc[:-1]
    y = label_next_up(df)
    y = y.loc[feats.index]
    X = feats[FEATS].astype(float).values
    if len(y) < 100:
        print(f"[train][skip] too few samples {sym} {tf} n={len(y)}")
        return
    from sklearn.ensemble import RandomForestClassifier
    clf = RandomForestClassifier(n_estimators=400, max_depth=6, min_samples_leaf=5, n_jobs=-1, random_state=42)
    clf.fit(X, y.values)
    out = MODELS / f"pro_{sym}_{tf}.joblib"
    dump(clf, out)
    meta = {
        "symbol": sym, "tf": tf, "feats": FEATS,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    }
    (MODELS / f"pro_{sym}_{tf}.json").write_text(json.dumps(meta, indent=2))
    print(f"[train][ok] {out}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=None)
    ap.add_argument("--timeframes", nargs="+", default=None)
    ap.add_argument("--lookback-days", type=int, default=int(os.getenv("EVAL_LOOKBACK_DAYS","365")))
    args = ap.parse_args()

    syms = args.symbols or env_list("SYMBOLS", "BTCUSDT,ETHUSDT,ADAUSDT,SOLUSDT,XRPUSDT")
    tfs  = args.timeframes or env_list("TFS",    "15m,1h,4h")
    for s in syms:
        for tf in tfs:
            try:
                train_one(s, tf, args.lookback_days)
            except Exception as e:
                print(f"[train][fail] {s} {tf}: {e}")

if __name__ == "__main__":
    main()
