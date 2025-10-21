#!/usr/bin/env python3
# tools/paper_trade.py — kevyt skeleton, yhteensopiva CLI:n kanssa

import argparse
import json
import os
import pandas as pd


def atr(high, low, close, period=14):
    high = pd.Series(high).astype(float)
    low = pd.Series(low).astype(float)
    close = pd.Series(close).astype(float)
    prev_close = close.shift(1)

    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    return tr.ewm(alpha=1 / period, adjust=False).mean()


def ensure_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    # Kolumnien case-insensitive haku & aliakset
    lc = {c.lower(): c for c in df.columns}

    def pick(*names):
        for n in names:
            if n in lc:
                return lc[n]
        return None

    hi = pick("high", "h")
    lo = pick("low", "l")
    cl = pick("close", "c")

    missing = [n for n, c in [("high", hi), ("low", lo), ("close", cl)] if c is None]
    if missing:
        raise ValueError(f"CSV:lta puuttuu kolumnit: {', '.join(missing)}")

    if "ATR" not in df.columns:
        df["ATR"] = atr(df[hi], df[lo], df[cl], period=int(period))

    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="Path to trained model (unused in smoketest)")
    ap.add_argument("--csv", required=True, help="Historical OHLCV CSV")
    ap.add_argument("--thr", required=True, type=float, help="Decision threshold (echoed to output)")
    ap.add_argument("--equity0", default=10000.0, type=float, help="Starting equity (echoed)")
    ap.add_argument("--out", default="results/paper_smoke.json", help="Output JSON path")
    args = ap.parse_args()

    df = pd.read_csv(args.csv)

    # Yhdenmukaista 'timestamp' → 'time' jos tarpeen
    if "timestamp" in df.columns and "time" not in df.columns:
        df = df.rename(columns={"timestamp": "time"})

    # ATR-periodi: env tai oletus
    atr_period = int(os.environ.get("ATR_PERIOD", "14"))
    df = ensure_atr(df, period=atr_period)

    out = {
        "rows": int(len(df)),
        "has_ATR": "ATR" in df.columns,
        "atr_na": int(df["ATR"].isna().sum()),
        "thr": float(args.thr),
        "equity0": float(args.equity0),
        "csv": os.path.basename(args.csv),
        "ok": True,
    }

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
