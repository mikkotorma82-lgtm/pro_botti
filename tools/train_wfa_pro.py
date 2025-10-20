from __future__ import annotations
import os, json, time, itertools
from pathlib import Path
from typing import Dict, Any, List, Tuple
import numpy as np
import pandas as pd
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

# Sallittujen indikaattorien nimet
ALL_INDICS = ["sma", "ema", "rsi", "macd", "adx", "atr", "vola", "obv"]
INDIC_PARAMS = {
    "sma": {"sma_n": [10, 20, 50]},
    "ema": {"ema_n": [21, 50]},
    "rsi": {"rsi_n": [14], "rsi_low": [30.0], "rsi_high": [70.0]},
    "macd": {"macd_fast": [12], "macd_slow": [26], "macd_sig": [9]},
    # Lisää muut indikaattorit parametreineen tarvittaessa
}

def _grid(indics: List[str]) -> List[Dict[str, Any]]:
    """Generoi kaikki sallittujen indikaattorien yhdistelmät (3–5 kpl) ja niiden parametrit"""
    grids = []
    for combo in itertools.combinations(indics, r=3):
        param_sets = []
        for name in combo:
            param_sets.append(list(itertools.product(*INDIC_PARAMS.get(name, {}).values())))
        for params_combo in itertools.product(*param_sets):
            cfg = {"indicators": combo, "params": {}, "weights": {}, "threshold": 0.3}
            for i, name in enumerate(combo):
                keys = list(INDIC_PARAMS[name].keys())
                for k, v in zip(keys, params_combo[i]):
                    cfg["params"][k] = v
                cfg["weights"][name] = 1.0
            # Kokeile thresholdia 0.3 ja 0.5
            for thr in [0.3, 0.5]:
                cfg_copy = cfg.copy()
                cfg_copy["threshold"] = thr
                grids.append(cfg_copy)
    return grids

def _metrics(ret: np.ndarray) -> Dict[str, float]:
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
    registry: List[Dict[str, Any]] = []
    grid_indics = ["sma","ema","rsi","macd"] # Voit muuttaa tähän sallittavat
    print(f"[TRAIN] symbols={len(symbols)} TFs={tfs} folds={folds} page_size={page_size} page_sleep={sleep_sec}", flush=True)
    for sym in symbols:
        for tf in tfs:
            try:
                df = capital_get_candles_df(sym, tf, total_limit=max_total, page_size=page_size, sleep_sec=sleep_sec)
                if df.empty or len(df) < 600:
                    print(f"[WARN] not enough data {sym} {tf} (rows={len(df)})", flush=True); continue
                best = None
                best_cfg = None
                best_ret = None
                for cfg in _grid(grid_indics):
                    # Rakennetaan signaali ja simuloidaan (täällä voit käyttää ML-mallia jos haluat)
                    sig = consensus_signal(df, cfg)
                    ret = simulate_returns(df, sig, fee_bps, slip_bps, spread_bps, position_mode)
                    metrics = _metrics(ret)
                    score = metrics["pf"] # Voit käyttää muitakin metriikoita
                    if (best is None) or (score > best):
                        best = score
                        best_cfg = cfg
                        best_ret = ret
                if best_cfg is None:
                    print(f"[WARN] no result {sym} {tf}", flush=True); continue
                row = {"symbol": sym, "tf": tf, "strategy": "CONSENSUS", "config": best_cfg, "metrics": _metrics(best_ret),
                       "costs_bps": {"fee": fee_bps, "slip": slip_bps, "spread": spread_bps},
                       "sr_filter": sr_filter, "position_mode": position_mode, "trained_at": int(time.time())}
                registry.append(row)
                # Talleta malli tiedostoon
                fn = f"{sym.replace('/', '').replace(' ', '')}__{tf}.joblib"
                dump(best_cfg, MODEL_DIR / fn)
                print(f"[OK] {sym} {tf} -> pf={row['metrics']['pf']:.2f} thr={best_cfg['threshold']} cfg={best_cfg['indicators']}", flush=True)
                time.sleep(0.3)
            except Exception as e:
                print(f"[ERROR] training failed for {sym} {tf}: {e}", flush=True)
    with open(REG_PATH, "w") as f:
        json.dump({"models": registry}, f, ensure_ascii=False, indent=2)
    print(f"[DONE] models -> {REG_PATH} (count={len(registry)})", flush=True)

if __name__ == "__main__":
    main()
