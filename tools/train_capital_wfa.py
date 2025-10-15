#!/usr/bin/env python3
from __future__ import annotations
import os
import json
import time
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd

from tools.capital_session import (
    capital_rest_login,
    capital_get_candles_df,
)
from tools.wfa import wfa_one

ROOT = Path(__file__).resolve().parents[1]
CAP_DIR = ROOT / "data" / "capital"
CAP_DIR.mkdir(parents=True, exist_ok=True)
STATE_DIR = ROOT / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
REGISTRY_PATH = STATE_DIR / "models_sma.json"

DEFAULT_TFS = ["15m", "1h", "4h"]

def _read_symbols_from_env() -> List[str]:
    # Prefer TRADE_SYMBOLS then CAPITAL_SYMBOLS
    raw = os.getenv("TRADE_SYMBOLS") or os.getenv("CAPITAL_SYMBOLS") or ""
    syms = [s.strip() for s in raw.split(",") if s.strip()]
    if not syms:
        # fallback: minimal demo
        syms = ["US SPX 500", "EUR/USD", "GOLD", "AAPL", "BTC/USD"]
    return syms

def _safe_name(s: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in s)

def _write_csv(df: pd.DataFrame, symbol: str, tf: str) -> Path:
    out = CAP_DIR / f"{_safe_name(symbol)}__{tf}.csv"
    df.to_csv(out, index=False)
    return out

def _pick_best_param_from_wfa_detail(res: Dict[str, Any]) -> int:
    # Enemmistö paras 'n' foldien yli; tasatilanteessa pienin
    ns = [int(d["n"]) for d in res.get("detail", []) if "n" in d]
    if not ns:
        return 20
    # mode
    counts = {}
    for n in ns:
        counts[n] = counts.get(n, 0) + 1
    best_n = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return int(best_n)

def main():
    # Hae env ja lämmitä login
    capital_rest_login()
    symbols = _read_symbols_from_env()
    tfs = [s.strip() for s in (os.getenv("TRAIN_TFS") or "").split(",") if s.strip()] or DEFAULT_TFS
    lookback_days = int(os.getenv("TRAIN_LOOKBACK_DAYS", "180"))
    max_total = int(os.getenv("TRAIN_MAX_TOTAL", "10000"))
    page_size = int(os.getenv("TRAIN_PAGE_SIZE", "200"))
    sleep_sec = float(os.getenv("TRAIN_PAGE_SLEEP", "1.0"))

    print(f"[INFO] Training SMA WFA for {len(symbols)} symbols, TFs={tfs}")
    registry: List[Dict[str, Any]] = []

    for sym in symbols:
        for tf in tfs:
            # Backfill → DataFrame
            print(f"[DATA] {sym} {tf} fetching ~{lookback_days}d (cap={max_total}) ...")
            df = capital_get_candles_df(sym, tf, total_limit=max_total, page_size=page_size, sleep_sec=sleep_sec)
            if df.empty or len(df) < 400:
                print(f"[WARN] no/enough data for {sym} {tf}, rows={len(df)}")
                continue
            # Kirjoita CSV WFA:lle
            csv_path = _write_csv(df, sym, tf)
            print(f"[OK] wrote {len(df)} rows -> {csv_path}")

            # WFA
            print(f"[WFA] {sym} {tf} ...")
            res = wfa_one(str(csv_path), folds=6)
            best_n = _pick_best_param_from_wfa_detail(res)
            row = {
                "symbol": sym,
                "tf": tf,
                "strategy": "SMA",
                "params": {"n": best_n},
                "metrics": {
                    "folds": res.get("folds", 0),
                    "sharpe_oos_mean": res.get("sharpe_oos_mean", 0.0),
                    "pf_oos_mean": res.get("pf_oos_mean", 1.0),
                    "wr_oos_mean": res.get("wr_oos_mean", 0.0),
                    "cagr_oos_prod": res.get("cagr_oos_prod", 0.0),
                    "maxdd_oos_min": res.get("maxdd_oos_min", 0.0),
                },
                "csv": str(csv_path),
                "time": int(time.time()),
            }
            registry.append(row)
            print(f"[OK] {sym} {tf} -> n={best_n} sharpe_oos={row['metrics']['sharpe_oos_mean']:.3f}")

            # Ole kiltti WAF:lle
            time.sleep(0.8)

    # Tallenna registry
    with open(REGISTRY_PATH, "w") as f:
        json.dump({"models": registry}, f, ensure_ascii=False, indent=2)
    print(f"[DONE] Registry -> {REGISTRY_PATH} (models={len(registry)})")

if __name__ == "__main__":
    main()
