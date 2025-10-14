#!/usr/bin/env python3
from __future__ import annotations
import os, json, time
from pathlib import Path
from typing import List
import numpy as np
import pandas as pd
from joblib import load
from tools.data_sources import fetch_ohlcv

ROOT   = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"

def log(s: str):
    ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    print(f"[{ts}] {s}", flush=True)

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

class ModelBook:
    def __init__(self):
        self.models = {}
        self.mtimes = {}
        self.feats  = {}

    def _model_path(self, s:str, tf:str) -> Path:
        return MODELS / f"pro_{s}_{tf}.joblib"

    def _meta_path(self, s:str, tf:str) -> Path:
        return MODELS / f"pro_{s}_{tf}.json"

    def ensure(self, s:str, tf:str) -> bool:
        p = self._model_path(s,tf)
        if not p.exists(): return False
        mt = p.stat().st_mtime
        key = (s,tf)
        if key not in self.mtimes or mt > self.mtimes[key]:
            self.models[key] = load(p)
            self.mtimes[key] = mt
            feats = ["ret1","ret5","vol5","ema12","ema26","macd","rsi14","atr14","ema_gap"]
            try:
                meta = json.loads(self._meta_path(s,tf).read_text())
                feats = meta.get("feats") or meta.get("features") or feats
            except Exception:
                pass
            self.feats[key] = feats
            log(f"[OK] loaded {p.name} (features={len(self.feats[key])})")
        return True

    def predict_proba(self, s:str, tf:str, X):
        from numpy import atleast_2d
        mdl = self.models[(s,tf)]
        return float(mdl.predict_proba(atleast_2d(X))[:,1][0])

def main():
    SYMS = env_list("SYMBOLS", "BTCUSDT,ETHUSDT,ADAUSDT,SOLUSDT,XRPUSDT")
    TFS  = env_list("TFS", "15m,1h,4h")
    POLL = int(os.getenv("POLL_SECS","60"))
    BUY  = float(os.getenv("BUY_THR","0.55"))
    SELL = float(os.getenv("SELL_THR","0.45"))

    mb = ModelBook()
    log(f"[INFO] live start: SYMBOLS={SYMS} TFS={TFS} POLL={POLL}s BUY_THR={BUY} SELL_THR={SELL}")
    while True:
        try:
            SYMS = env_list("SYMBOLS", ",".join(SYMS))
            TFS  = env_list("TFS", ",".join(TFS))
            for s in SYMS:
                for tf in TFS:
                    if not mb.ensure(s, tf):
                        log(f"[WARN] no_model {s} {tf}")
                        continue
                    try:
                        df = fetch_ohlcv(s, tf, lookback_days=365)
                    except Exception as e:
                        log(f"[WARN] fetch_fail {s} {tf}: {e}")
                        continue
                    feats = build_features(df)
                    if feats is None or feats.empty:
                        log(f"[WARN] no_features {s} {tf}")
                        continue
                    cols = mb.feats.get((s,tf)) or [c for c in feats.columns if c not in ("time","open","high","low","close","volume")]
                    x = feats[cols].astype(float).iloc[-1].values
                    p = mb.predict_proba(s, tf, x)
                    side = "HOLD"
                    if p >= BUY: side = "BUY"
                    elif p <= SELL: side = "SELL"
                    print(json.dumps({"symbol":s,"tf":tf,"side":side,"p":round(p,4)}), flush=True)
        except Exception as e:
            log(f"[ERROR] loop: {e}")
        time.sleep(POLL)

if __name__ == "__main__":
    main()
