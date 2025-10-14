#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, time
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import numpy as np, pandas as pd
from joblib import load

try:
    import ccxt  # type: ignore
except Exception:
    ccxt = None

ROOT   = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
STATE  = ROOT / "state"
STATE.mkdir(parents=True, exist_ok=True)

def env_list(name: str, default_csv: str) -> List[str]:
    v = os.getenv(name, default_csv)
    return [s.strip() for s in v.split(",") if s.strip()]

def to_ccxt_symbol(sym: str) -> str:
    if "/" in sym: return sym
    if sym.endswith("USDT"): return f"{sym[:-4]}/USDT"
    return sym

def tf_to_ccxt(tf: str) -> str: return tf.lower()

def fetch(sym: str, tf: str, lookback_days: int) -> pd.DataFrame:
    if ccxt is None: raise RuntimeError("ccxt puuttuu")
    ex = ccxt.binance({"enableRateLimit": True})
    since = int((time.time() - lookback_days*86400) * 1000)
    rows = []; last = since
    while True:
        batch = ex.fetch_ohlcv(to_ccxt_symbol(sym), timeframe=tf_to_ccxt(tf), since=last, limit=1000)
        if not batch: break
        rows.extend(batch)
        if len(batch) < 1000 or len(rows) >= 4000: break
        last = int(batch[-1][0]) + 1
    if not rows: return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["time","open","high","low","close","volume"])
    df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    return df

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    z = df.copy()
    c = pd.to_numeric(z["close"], errors="coerce")
    z["ret1"] = c.pct_change()
    z["ret5"] = c.pct_change(5)
    z["vol5"] = z["ret1"].rolling(5).std().fillna(0.0)
    z["ema12"] = c.ewm(span=12, adjust=False).mean()
    z["ema26"] = c.ewm(span=26, adjust=False).mean()
    z["macd"]  = z["ema12"] - z["ema26"]
    diff = c.diff()
    up = diff.clip(lower=0).rolling(14).mean()
    dn = (-diff.clip(upper=0)).rolling(14).mean()
    rs = up / dn.replace(0, np.nan)
    z["rsi14"] = 100 - (100 / (1 + rs))
    tr = np.maximum(
        z["high"] - z["low"],
        np.maximum((z["high"] - z["close"].shift()).abs(), (z["low"] - z["close"].shift()).abs()),
    )
    z["atr14"] = tr.rolling(14).mean()
    z["ema_gap"] = (c - z["ema12"]) / z["ema12"]
    z = z.replace([np.inf,-np.inf], np.nan).dropna()
    return z

FEATS = ["ret1","ret5","vol5","ema12","ema26","macd","rsi14","atr14","ema_gap"]

def pct_returns_from_close(df: pd.DataFrame) -> np.ndarray:
    s = pd.to_numeric(df["close"], errors="coerce")
    return s.pct_change().fillna(0.0).to_numpy()

def max_drawdown(eq: np.ndarray) -> float:
    if eq.size == 0: return 0.0
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    return float(abs(dd.min()))

def profit_factor(r: np.ndarray) -> float:
    g = r[r>0].sum()
    l = -r[r<0].sum()
    return float(g/l) if l>0 else (float("inf") if g>0 else 0.0)

def sharpe(r: np.ndarray, periods_per_year: float) -> float:
    if r.size == 0: return 0.0
    std = r.std(ddof=1)
    return float(r.mean()/std*np.sqrt(periods_per_year)) if std>0 else 0.0

def periods_py(tf: str) -> float:
    tf = tf.lower()
    if tf.endswith("m"): return 525600.0/int(tf[:-1])
    if tf.endswith("h"): return 8760.0/int(tf[:-1])
    if tf.endswith("d"): return 252.0/int(tf[:-1])
    return 8760.0

def simulate_longonly(returns: np.ndarray, probs: np.ndarray, buy: float, sell: float):
    n = min(len(returns), len(probs))
    r = returns[-n:]; p = probs[-n:]
    pos = np.zeros(n, dtype=float)
    holding = 0.0
    for i, pi in enumerate(p):
        if holding==0.0 and pi>=buy: holding=1.0
        elif holding==1.0 and pi<=sell: holding=0.0
        pos[i] = holding
    pos_shift = np.roll(pos, 1); pos_shift[0] = 0.0
    strat = pos_shift * r
    eq = np.cumprod(1.0 + strat)
    mdd = max_drawdown(eq)
    pf  = profit_factor(strat)
    wr  = float((strat>0).mean()) if strat.size else 0.0
    return strat, {"mdd":mdd, "pf":pf, "wr":wr}

def evaluate_one(sym: str, tf: str, lookback_days: int, buy: float, sell: float) -> Optional[Dict]:
    model_p = MODELS / f"pro_{sym}_{tf}.joblib"
    if not model_p.exists():
        print(f"[eval][skip] no model {sym} {tf}")
        return None
    df = fetch(sym, tf, lookback_days)
    if df is None or df.empty:
        print(f"[eval][skip] no data {sym} {tf}")
        return None
    feats = build_features(df)
    if feats is None or feats.empty:
        print(f"[eval][skip] no features {sym} {tf}")
        return None
    clf = load(model_p)
    X = feats[FEATS].astype(float).values
    try:
        P = clf.predict_proba(X)[:,1]
    except Exception:
        return None
    r = pct_returns_from_close(df)[-len(P):]
    strat, det = simulate_longonly(r, P, buy, sell)
    py = periods_py(tf)
    return {
        "symbol": sym, "tf": tf,
        "sharpe": sharpe(strat, py),
        "pf": det["pf"],
        "mdd": det["mdd"],
        "wr": det["wr"],
        "score": 0.5*sharpe(strat, py) + 0.3*det["pf"] + 0.2*(1.0 - min(1.0, det["mdd"])),
        "trades": int((np.diff(np.r_[0,(strat!=0).astype(int)])!=0).sum()//2)
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", required=True)
    ap.add_argument("--timeframes", nargs="+", required=True)
    ap.add_argument("--lookback-days", type=int, default=365)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--min-trades", type=int, default=10)
    ap.add_argument("--buy-thr", type=float, default=float(os.getenv("BUY_THR","0.55")))
    ap.add_argument("--sell-thr", type=float, default=float(os.getenv("SELL_THR","0.45")))
    args = ap.parse_args()

    rows: List[Dict] = []
    for s in args.symbols:
        for tf in args.timeframes:
            try:
                r = evaluate_one(s, tf, args.lookback_days, args.buy_thr, args.sell_thr)
                if r: rows.append(r)
            except Exception as e:
                print(f"[eval][fail] {s} {tf}: {e}")

    best_by_sym: Dict[str,Dict] = {}
    for r in rows:
        sym = r["symbol"]
        if sym not in best_by_sym or r["score"] > best_by_sym[sym]["score"]:
            best_by_sym[sym] = r
    elig = [x for x in best_by_sym.values() if x["trades"] >= args.min_trades]
    if not elig: elig = list(best_by_sym.values())
    top = sorted(elig, key=lambda z: z["score"], reverse=True)[:args.top_k]

    selection = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        "timeframes": args.timeframes,
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
        "notes": "Model-based selection using RandomForest + ccxt/binance data."
    }
    (STATE / "active_symbols.json").write_text(json.dumps(selection, indent=2, ensure_ascii=False))
    print("[selection-model] -> state/active_symbols.json")
    print(json.dumps(selection, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
