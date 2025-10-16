#!/usr/bin/env python3
from __future__ import annotations
import os, json, time
from pathlib import Path
from typing import Dict, Any, List

import numpy as np
import pandas as pd

from tools.capital_session import capital_rest_login, capital_get_candles_df
from tools.exec_sim import simulate_returns
from tools.consensus_engine import consensus_signal
from tools.support_resistance import pivots
from tools.symbol_resolver import read_symbols

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
REG_PATH = STATE_DIR / "models_pro.json"

DEFAULT_TFS = ["15m", "1h", "4h"]

def _grid() -> List[Dict[str, Any]]:
    grid = []
    for sma_n in [10, 20, 50]:
        for ema_n in [21, 50]:
            for rsi_n in [14]:
                for thr in [0.3, 0.5]:
                    cfg = {
                        "weights": {"sma": 1.0, "ema": 1.0, "rsi": 0.5, "macd": 1.0},
                        "params": {
                            "sma_n": sma_n, "ema_n": ema_n, "rsi_n": rsi_n,
                            "rsi_low": 30.0, "rsi_high": 70.0,
                            "macd_fast": 12, "macd_slow": 26, "macd_sig": 9
                        },
                        "threshold": thr
                    }
                    grid.append(cfg)
    return grid

def _metrics(ret: np.ndarray) -> Dict[str, float]:
    if ret.size == 0:
        return {"sh":0.0, "pf":1.0, "wr":0.0, "cagr":0.0, "maxdd":0.0}
    mu = ret.mean()
    sd = ret.std(ddof=1) or 1e-12
    sh = float(mu / sd)
    gains = ret[ret > 0].sum()
    losses = -ret[ret < 0].sum()
    pf = float(gains / losses) if losses > 0 else float("inf")
    wr = float((ret > 0).mean())
    eq = np.cumprod(1.0 + ret)
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    maxdd = float(dd.min())
    cagr = float(np.exp(np.log1p(ret).sum()) - 1.0)
    return {"sh":sh, "pf":pf, "wr":wr, "cagr":cagr, "maxdd":maxdd}

def _wfa(df: pd.DataFrame, cfg: Dict[str, Any], folds: int,
         fee_bps: float, slip_bps: float, spread_bps: float,
         sr_filter: bool, position_mode: str) -> Dict[str, Any]:

    T = len(df)
    fold_len = T // (folds + 1)
    details = []
    for i in range(folds):
        train_lo, train_hi = 0, (i+1)*fold_len
        test_lo,  test_hi  = train_hi, min((i+2)*fold_len, T)
        dtrain = df.iloc[train_lo:train_hi].copy()
        dtest  = df.iloc[test_lo:test_hi].copy()
        if len(dtest) < 100:
            break

        sig_train = consensus_signal(dtrain, cfg)
        sig_test  = consensus_signal(dtest,  cfg)

        if sr_filter:
            piv_train = pivots(dtrain, left=3, right=3)
            piv_test  = pivots(dtest, left=3, right=3)
            mask_train = (~piv_train["pivot_high"]) | (~piv_train["pivot_low"])
            mask_test  = (~piv_test["pivot_high"])  | (~piv_test["pivot_low"])
            sig_train = sig_train * mask_train.astype(float).values
            sig_test  = sig_test  * mask_test.astype(float).values

        r_train, _ = simulate_returns(dtrain, sig_train, fee_bps, slip_bps, spread_bps, position_mode)
        r_test,  _ = simulate_returns(dtest,  sig_test,  fee_bps, slip_bps, spread_bps, position_mode)
        m = _metrics(r_test)
        details.append({"metrics": m})

    agg = {
        "folds": len(details),
        "sh_oos_mean": float(np.mean([d["metrics"]["sh"] for d in details])) if details else 0.0,
        "pf_oos_mean": float(np.mean([d["metrics"]["pf"] for d in details])) if details else 1.0,
        "wr_oos_mean": float(np.mean([d["metrics"]["wr"] for d in details])) if details else 0.0,
        "cagr_oos_prod": float(np.prod([1+d["metrics"]["cagr"] for d in details]) - 1.0) if details else 0.0,
        "maxdd_oos_min": float(np.min([d["metrics"]["maxdd"] for d in details])) if details else 0.0,
        "detail": details,
    }
    return agg

def main():
    capital_rest_login()
    symbols = read_symbols()
    tfs = [s.strip() for s in (os.getenv("TRAIN_TFS") or "").split(",") if s.strip()] or DEFAULT_TFS
    folds = int(os.getenv("TRAIN_FOLDS", "6"))
    max_total = int(os.getenv("TRAIN_MAX_TOTAL", "10000"))
    page_size = int(os.getenv("TRAIN_PAGE_SIZE", "200"))
    sleep_sec = float(os.getenv("TRAIN_PAGE_SLEEP", "1.0"))

    fee_bps = float(os.getenv("SIM_FEE_BPS", "1.0"))
    slip_bps = float(os.getenv("SIM_SLIP_BPS", "1.5"))
    spread_bps = float(os.getenv("SIM_SPREAD_BPS", "0.5"))
    sr_filter = bool(int(os.getenv("SIM_SR_FILTER", "1")))
    position_mode = os.getenv("SIM_POSITION_MODE", "longflat")

    grid = _grid()
    registry: List[Dict[str, Any]] = []
    print(f"[TRAIN] symbols={len(symbols)} TFs={tfs} folds={folds} costs(bps) fee={fee_bps} slip={slip_bps} spread={spread_bps} sr_filter={sr_filter} mode={position_mode}")

    for sym in symbols:
        for tf in tfs:
            df = capital_get_candles_df(sym, tf, total_limit=max_total, page_size=page_size, sleep_sec=sleep_sec)
            if df.empty or len(df) < 600:
                print(f"[WARN] not enough data {sym} {tf} (rows={len(df)})")
                continue

            best = None
            for cfg in grid:
                res = _wfa(df, cfg, folds, fee_bps, slip_bps, spread_bps, sr_filter, position_mode)
                score = (res["sh_oos_mean"], res["pf_oos_mean"])
                if (best is None) or (score > best[0]):
                    best = (score, cfg, res)

            if best is None:
                print(f"[WARN] no result {sym} {tf}")
                continue

            score, cfg, res = best
            row = {
                "symbol": sym, "tf": tf,
                "strategy": "CONSENSUS",
                "config": cfg,
                "metrics": res,
                "costs_bps": {"fee": fee_bps, "slip": slip_bps, "spread": spread_bps},
                "sr_filter": sr_filter, "position_mode": position_mode,
                "trained_at": int(time.time())
            }
            registry.append(row)
            print(f"[OK] {sym} {tf} -> sh={res['sh_oos_mean']:.3f} pf={res['pf_oos_mean']:.2f} thr={cfg['threshold']} cfg={cfg['params']}")
            time.sleep(0.8)

    with open(REG_PATH, "w") as f:
        json.dump({"models": registry}, f, ensure_ascii=False, indent=2)
    print(f"[DONE] models -> {REG_PATH} (count={len(registry)})")

if __name__ == "__main__":
    main()
