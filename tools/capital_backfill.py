#!/usr/bin/env python3
from __future__ import annotations
import argparse
import os
from pathlib import Path
import time

import pandas as pd
from tools.capital_session import capital_rest_login, capital_get_candles_df

OUT_DIR = Path(os.getenv("CAPITAL_CACHE_DIR", "data/capital")).resolve()
OUT_DIR.mkdir(parents=True, exist_ok=True)

BARS_PER_DAY = {
    "15m": 96,
    "1h": 24,
    "4h": 6,
    "1d": 1,
}

def safe_name(s: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in s)

def estimate_total(tf: str, lookback_days: int, max_cap: int) -> int:
    bpd = BARS_PER_DAY.get(tf.lower(), 24)
    return min(max_cap, lookback_days * bpd)

def write_outputs(df: pd.DataFrame, symbol: str, tf: str, fmt: str) -> Path:
    base = f"{safe_name(symbol)}__{tf}"
    p = OUT_DIR / f"{base}.{ 'parquet' if fmt=='parquet' else 'csv'}"
    if fmt == "parquet":
        df.to_parquet(p, index=False)
    else:
        df.to_csv(p, index=False)
    return p

def main():
    ap = argparse.ArgumentParser(description="Backfill Capital.com OHLCV to local cache")
    ap.add_argument("--symbols", nargs="+", required=True, help='Symbols or EPICs, e.g. "US SPX 500" "EUR/USD" "GOLD" "AAPL" "BTC/USD"')
    ap.add_argument("--timeframes", nargs="+", default=["15m","1h","4h"], help="TF list, e.g. 15m 1h 4h")
    ap.add_argument("--lookback-days", type=int, default=180, help="How many days to backfill")
    ap.add_argument("--max-total", type=int, default=10000, help="Hard limit of total bars per TF")
    ap.add_argument("--page-size", type=int, default=200, help="Page size per request")
    ap.add_argument("--sleep-sec", type=float, default=1.0, help="Sleep between page requests")
    ap.add_argument("--fmt", choices=["parquet","csv"], default="parquet", help="Output format")
    args = ap.parse_args()

    # warm login
    capital_rest_login()

    for sym in args.symbols:
        for tf in args.timeframes:
            total = estimate_total(tf, args.lookback_days, args.max_total)
            print(f"[{sym}] {tf}: target bars ~{total}")
            df = capital_get_candles_df(sym, tf, total_limit=total, page_size=args.page_size, sleep_sec=args.sleep_sec)
            if df.empty:
                print(f"[WARN] no data for {sym} {tf}")
                continue
            p = write_outputs(df, sym, tf, args.fmt)
            print(f"[OK] wrote {len(df)} rows -> {p}")
            time.sleep(1.2)

if __name__ == "__main__":
    main()
