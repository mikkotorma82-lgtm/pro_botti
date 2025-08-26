#!/usr/bin/env python3
import argparse, json
import numpy as np, pandas as pd
from pathlib import Path

DROP_TIME = ["time", "date", "datetime", "timestamp", "open_time", "close_time"]


def backtest(y_true: np.ndarray, pos: np.ndarray, fee_bps: float = 3.0):
    y = y_true.astype(int)
    pos = pos.astype(int)
    trades = np.abs(np.diff(np.r_[0, pos]))
    gross = pos * (2 * y - 1)  # +1 jos oikein long, -1 jos väärin, 0 jos flat
    fees = trades * (fee_bps / 10000.0)
    pnl = gross - fees
    eq = np.cumsum(pnl)
    stats = {
        "pnl_sum": float(pnl.sum()),
        "pnl_mean": float(pnl.mean()),
        "trades": int(trades.sum()),
        "hit_rate": float((gross > 0).mean()),
        "max_dd": float(np.max(np.maximum.accumulate(eq) - eq)) if len(eq) else 0.0,
    }
    return eq, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data_csv", required=True)
    ap.add_argument("--preds_csv", required=True)
    ap.add_argument("--fee_bps", type=float, default=3.0)
    ap.add_argument("--use_proba", action="store_true")
    ap.add_argument("--thr", type=float, default=0.5)
    ap.add_argument("--out_prefix", required=True)
    args = ap.parse_args()

    data = pd.read_csv(args.data_csv)
    preds = pd.read_csv(args.preds_csv)

    # siivoa mahdolliset aikakolumnit pois
    drop = [c for c in DROP_TIME if c in data.columns]
    if drop:
        data.drop(columns=drop, inplace=True)

    y = data["target"].astype(int).values
    if args.use_proba and "proba" in preds:
        pos = (preds["proba"].values >= args.thr).astype(int)
    else:
        pos = preds["signal"].astype(int).values

    eq, stats = backtest(y, pos, args.fee_bps)

    out_eq = Path(f"{args.out_prefix}_equity.csv")
    out_js = Path(f"{args.out_prefix}_stats.json")
    pd.DataFrame({"equity": eq}).to_csv(out_eq, index=False)
    out_js.write_text(json.dumps(stats, indent=2))
    print(f"Saved: {out_eq}, {out_js}")


if __name__ == "__main__":
    main()
