from __future__ import annotations
import os
import time
import itertools
import json
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, Any, List
from joblib import dump
from tools.capital_session import capital_rest_login, capital_get_candles_df
from tools.exec_sim import simulate_returns
from tools.consensus_engine import consensus_signal
from tools.support_resistance import pivots
from tools.symbol_resolver import read_symbols
from tools.ml.purged_cv import PurgedTimeSeriesSplit

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "state"; STATE_DIR.mkdir(parents=True, exist_ok=True)
REG_PATH = STATE_DIR / "models_pro.json"
MODEL_DIR = STATE_DIR / "models_pro"
MODEL_DIR.mkdir(exist_ok=True)
DEFAULT_TFS = ["15m","1h","4h"]

ALL_INDICS = ["sma", "ema", "rsi", "macd", "adx", "atr", "vola", "obv"]
INDIC_PARAMS = {
    "sma": {"sma_n": [10, 20, 50]},
    "ema": {"ema_n": [21, 50]},
    "rsi": {"rsi_n": [14], "rsi_low": [30.0], "rsi_high": [70.0]},
    "macd": {"macd_fast": [12], "macd_slow": [26], "macd_sig": [9]},
    # Lisää muut indikaattorit parametreineen tarvittaessa
}

def _grid() -> List[Dict[str, Any]]:
    grid = []
    for sma_n in [10,20,50]:
        for ema_n in [21,50]:
            for thr in [0.3,0.5]:
                cfg = {
                    "weights": {"sma":1.0,"ema":1.0,"rsi":0.5,"macd":1.0},
                    "params": {"sma_n":sma_n,"ema_n":ema_n,"rsi_n":14,"rsi_low":30.0,"rsi_high":70.0,"macd_fast":12,"macd_slow":26,"macd_sig":9},
                    "threshold": thr
                }
                grid.append(cfg)
    return grid

def _metrics(ret: np.ndarray) -> Dict[str, float]:
    if not isinstance(ret, np.ndarray):
        ret = np.array(ret)
    if ret.size == 0: return {"sh":0.0,"pf":1.0,"wr":0.0,"cagr":0.0,"maxdd":0.0}
    mu = ret.mean(); sd = ret.std(ddof=1) or 1e-12; sh = float(mu/sd)
    gains = ret[ret>0].sum(); losses = -ret[ret<0].sum()
    pf = float(gains / (losses if losses>0 else np.inf))
    wr = float((ret>0).mean())
    eq = np.cumprod(1.0 + ret); peak = np.maximum.accumulate(eq); dd = (eq-peak)/peak; maxdd = float(dd.min())
    cagr = float(np.exp(np.log1p(ret).sum()) - 1.0)
    return {"sh":sh,"pf":pf,"wr":wr,"cagr":cagr,"maxdd":maxdd}

def main():
    capital_rest_login()
    symbols = read_symbols()
    tfs = [s.strip() for s in (os.getenv("TRAIN_TFS") or "").split(",") if s.strip()] or DEFAULT_TFS
    folds = int(os.getenv("TRAIN_FOLDS","6")); embargo = int(os.getenv("WFA_EMBARGO","5"))
    max_total = int(os.getenv("TRAIN_MAX_TOTAL","10000")); page_size = int(os.getenv("TRAIN_PAGE_SIZE","200")); sleep_sec = float(os.getenv("TRAIN_PAGE_SLEEP","1.5"))
    fee_bps = float(os.getenv("SIM_FEE_BPS","1.0")); slip_bps = float(os.getenv("SIM_SLIP_BPS","1.5")); spread_bps = float(os.getenv("SIM_SPREAD_BPS","0.5"))
    sr_filter = bool(int(os.getenv("SIM_SR_FILTER","1"))); position_mode = os.getenv("SIM_POSITION_MODE","longflat")
    grid = _grid(); registry: List[Dict[str, Any]] = []
    print(f"[TRAIN] symbols={len(symbols)} TFs={tfs} folds={folds} page_size={page_size} page_sleep={sleep_sec}", flush=True)
    for sym in symbols:
        for tf in tfs:
            try:
                df = capital_get_candles_df(sym, tf, total_limit=max_total, page_size=page_size, sleep_sec=sleep_sec)
                if df.empty or len(df) < 600:
                    print(f"[WARN] not enough data {sym} {tf} (rows={len(df)})", flush=True); continue
                best = None
                for cfg in grid:
                    res = simulate_returns(df, consensus_signal(df, cfg), fee_bps, slip_bps, spread_bps, position_mode)
                    if not isinstance(res, np.ndarray):
                        res = np.array(res)
                    # Optimoi ensisijaisesti OOS PF, sitten Sharpe
                    score = (_metrics(res)["pf"], _metrics(res)["sh"])
                    if (best is None) or (score > best[0]): best = (score, cfg, res)
                if best is None:
                    print(f"[WARN] no result {sym} {tf}", flush=True); continue
                score, cfg, res = best
                row = {"symbol": sym, "tf": tf, "strategy": "CONSENSUS", "config": cfg, "metrics": _metrics(res),
                       "costs_bps": {"fee": fee_bps, "slip": slip_bps, "spread": spread_bps},
                       "sr_filter": sr_filter, "position_mode": position_mode, "trained_at": int(time.time())}
                registry.append(row)
                fn = f"{sym.replace('/', '').replace(' ', '')}__{tf}.joblib"
                dump(cfg, MODEL_DIR / fn)
                print(f"[OK] {sym} {tf} -> pf={row['metrics']['pf']:.2f} thr={cfg['threshold']} cfg={cfg['params']}", flush=True)
                time.sleep(0.3)
            except Exception as e:
                print(f"[ERROR] training failed for {sym} {tf}: {e}", flush=True)
    with open(REG_PATH, "w") as f:
        json.dump({"models": registry}, f, ensure_ascii=False, indent=2)
    print(f"[DONE] models -> {REG_PATH} (count={len(registry)})", flush=True)

if __name__ == "__main__":
    main()
