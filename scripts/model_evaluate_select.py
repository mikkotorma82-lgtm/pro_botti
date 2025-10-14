#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, time
from pathlib import Path
from typing import List, Dict, Optional
import numpy as np, pandas as pd
from joblib import load
from tools.data_sources import fetch_ohlcv

ROOT   = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
STATE  = ROOT / "state"
STATE.mkdir(parents=True, exist_ok=True)

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

def pct_returns(close: pd.Series) -> np.ndarray:
    s = pd.to_numeric(close, errors="coerce")
    return s.pct_change().fillna(0.0).to_numpy()

def max_drawdown(eq: np.ndarray) -> float:
    if eq.size == 0: return 0.0
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    return float(abs(dd.min()))

def profit_factor(r: np.ndarray) -> float:
    g = r[r>0].sum(); l = -r[r<0].sum()
    return float(g/l) if l>0 else (float("inf") if g>0 else 0.0)

def sharpe(r: np.ndarray, periods_per_year: float) -> float:
    if r.size == 0: return 0.0
    sd = r.std(ddof=1)
    return float(r.mean()/sd*np.sqrt(periods_per_year)) if sd>0 else 0.0

def periods_py(tf: str) -> float:
    tf = tf.lower()
    if tf.endswith("m"): return 525600.0/int(tf[:-1])
    if tf.endswith("h"): return 8760.0/int(tf[:-1])
    if tf.endswith("d"): return 252.0/int(tf[:-1])
    return 8760.0

def simulate_longonly(returns: np.ndarray, probs: np.ndarray, buy: float, sell: float):
    n = min(len(returns), len(probs))
    r = returns[-n:]; p = probs[-n:]
    pos = np.zeros(n, dtype=float); holding = 0.0
    for i, pi in enumerate(p):
        if holding==0.0 and pi>=buy: holding=1.0
        elif holding==1.0 and pi<=sell: holding=0.0
        pos[i] = holding
    pos_shift = np.roll(pos, 1); pos_shift[0] = 0.0
    strat = pos_shift * r
    eq = np.cumprod(1.0 + strat)
    mdd = max_drawdown(eq); pf = profit_factor(strat)
    wr = float((strat>0).mean()) if strat.size else 0.0
    return strat, mdd, pf, wr

def evaluate_one(sym: str, tf: str, days: int, buy: float, sell: float) -> Optional[Dict]:
    mp = MODELS / f"pro_{sym}_{tf}.joblib"
    if not mp.exists():
        print(f"[eval][skip] no model {sym} {tf}")
        return None
    df = fetch_ohlcv(sym, tf, days)
    if df is None or df.empty:
        print(f"[eval][skip] no data {sym} {tf}")
        return None
    feats = build_features(df)
    if feats is None or feats.empty:
        print(f"[eval][skip] no features {sym} {tf}")
        return None
    clf = load(mp)
    X = feats[["ret1","ret5","vol5","ema12","ema26","macd","rsi14","atr14","ema_gap"]].astype(float).values
    try:
        P = clf.predict_proba(X)[:,1]
    except Exception:
        return None
    r = pct_returns(df["close"])[-len(P):]
    strat, mdd, pf, wr = simulate_longonly(r, P, buy, sell)
    py = periods_py(tf)
    s = sharpe(strat, py)
    score = 0.5*s + 0.3*pf + 0.2*(1.0 - min(1.0, mdd))
    trades = int((np.diff(np.r_[0,(strat!=0).astype(int)])!=0).sum()//2)
    return {"symbol":sym,"tf":tf,"sharpe":s,"pf":pf,"mdd":mdd,"wr":wr,"score":score,"trades":trades}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=None)
    ap.add_argument("--timeframes", nargs="+", default=None)
    ap.add_argument("--lookback-days", type=int, default=int(os.getenv("EVAL_LOOKBACK_DAYS","365")))
    ap.add_argument("--top-k", type=int, default=int(os.getenv("TOP_K","5")))
    ap.add_argument("--min-trades", type=int, default=int(os.getenv("MIN_TRADES","10")))
    ap.add_argument("--buy-thr", type=float, default=float(os.getenv("BUY_THR","0.55")))
    ap.add_argument("--sell-thr", type=float, default=float(os.getenv("SELL_THR","0.45")))
    args = ap.parse_args()

    syms = args.symbols or env_list("SYMBOLS", "BTCUSDT,ETHUSDT,ADAUSDT,SOLUSDT,XRPUSDT")
    tfs  = args.timeframes or env_list("TFS", "15m,1h,4h")

    rows: List[Dict] = []
    for s in syms:
        for tf in tfs:
            try:
                r = evaluate_one(s, tf, args.lookback_days, args.buy_thr, args.sell_thr)
                if r: rows.append(r)
            except Exception as e:
                print(f"[eval][fail] {s} {tf}: {e}")

    best: Dict[str,Dict] = {}
    for r in rows:
        sym = r["symbol"]
        if sym not in best or r["score"] > best[sym]["score"]:
            best[sym] = r
    elig = [x for x in best.values() if x["trades"] >= args.min_trades] or list(best.values())
    top = sorted(elig, key=lambda z: z["score"], reverse=True)[:args.top_k]

    sel = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        "timeframes": tfs,
        "top_k": args.top_k,
        "symbols": [r["symbol"] for r in top],
        "criteria": {
            "type": "model_based",
            "min_trades": args.min_trades,
            "buy_thr": args.buy_thr,
            "sell_thr": args.sell_thr,
            "lookback_days": args.lookback_days,
            "weights": {"sharpe":0.5,"profit_factor":0.3,"max_drawdown":0.2}
        },
        "notes": "Model-based selection using RF + ccxt/yfinance data.",
    }
    (STATE / "active_symbols.json").write_text(json.dumps(sel, indent=2, ensure_ascii=False))
    print("[selection-model] -> state/active_symbols.json")
    print(json.dumps(sel, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
