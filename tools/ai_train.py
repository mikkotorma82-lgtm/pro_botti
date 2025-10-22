#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CapitalBot – True Model Trainer (Live Data Mode)
Kouluttaa oikeat mallit käyttäen historian CSV-dataa.
"""

import os, json, datetime, time
import pandas as pd
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from xgboost import XGBRegressor
from sklearn.metrics import r2_score
import joblib

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"
MODELS = BASE / "models"
HIST = DATA / "train_history.json"
MODELS.mkdir(exist_ok=True)
DATA.mkdir(exist_ok=True)

SYMBOLS = ["BTCUSD","ETHUSD","EURUSD","US500"]
TIMEFRAMES = ["1h","4h"]

def load_data(symbol, tf):
    path = DATA / "history" / f"{symbol}_{tf}.csv"
    if not path.exists():
        print(f"[warn] no history for {symbol}_{tf}")
        return None
    df = pd.read_csv(path)
    if "close" not in df.columns:
        print(f"[warn] invalid file {path}")
        return None
    df["return"] = df["close"].pct_change().fillna(0)
    df["ma_fast"] = df["close"].rolling(10).mean()
    df["ma_slow"] = df["close"].rolling(50).mean()
    df["rsi"] = 100 - (100 / (1 + (df["close"].diff().clip(lower=0).rolling(14).mean() /
                                   df["close"].diff().clip(upper=0).abs().rolling(14).mean())))
    df = df.dropna().reset_index(drop=True)
    return df

def train_symbol(symbol, tf):
    df = load_data(symbol, tf)
    if df is None or len(df) < 500:
        return None
    X = df[["ma_fast","ma_slow","rsi"]]
    y = df["return"].shift(-1).fillna(0)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)
    model = XGBRegressor(n_estimators=300, learning_rate=0.05, max_depth=6, subsample=0.8)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    r2 = r2_score(y_test, y_pred)
    path = MODELS / f"{symbol}_{tf}_xgb.pkl"
    joblib.dump(model, path)
    print(f"[train] {symbol}_{tf} done, r2={r2:.3f}, saved {path.name}")
    return {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "status": "ok",
        "model": "XGBRegressor",
        "tf": tf,
        "symbol": symbol,
        "sharpe": round(r2*2, 3),  # R2 → Sharpe-like
        "notes": f"r2={r2:.3f}"
    }

def append_history(entry):
    hist = []
    if HIST.exists():
        try:
            hist = json.load(open(HIST))
        except Exception:
            pass
    hist.append(entry)
    json.dump(hist, open(HIST, "w"), indent=2)

def main():
    print("[trainer] starting true training ...")
    for sym in SYMBOLS:
        for tf in TIMEFRAMES:
            try:
                res = train_symbol(sym, tf)
                if res:
                    append_history(res)
                    time.sleep(1)
            except Exception as e:
                print(f"[error] {sym}_{tf}: {e}")
    print("[trainer] all done.")

if __name__ == "__main__":
    main()
