#!/usr/bin/env python3
from __future__ import annotations
import argparse
import glob
import json
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd
from tools.wfa import wfa_one

def main():
    ap = argparse.ArgumentParser(description="Run WFA over many CSVs and create a leaderboard")
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--csvs", nargs="+", help="Explicit CSV file paths")
    grp.add_argument("--glob", help="Glob pattern, e.g. 'data/capital/*__1h.csv'")
    ap.add_argument("--folds", type=int, default=6)
    ap.add_argument("--out", required=True, help="Output leaderboard CSV")
    ap.add_argument("--json-dir", help="Optional directory to write per-file JSON results")
    args = ap.parse_args()

    files: List[str] = args.csvs or glob.glob(args.glob or "")
    rows: List[Dict[str, Any]] = []
    json_dir = Path(args.json_dir) if args.json_dir else None
    if json_dir:
        json_dir.mkdir(parents=True, exist_ok=True)

    for fp in files:
        try:
            res = wfa_one(fp, folds=args.folds)
            # infer symbol/tf from filename like SYMBOL__TF.csv
            name = Path(fp).stem
            if "__" in name:
                symbol, tf = name.split("__", 1)
            else:
                symbol, tf = name, ""
            row = {
                "file": fp,
                "symbol": symbol,
                "tf": tf,
                "folds": res.get("folds", 0),
                "sharpe_oos_mean": res.get("sharpe_oos_mean", 0.0),
                "pf_oos_mean": res.get("pf_oos_mean", 1.0),
                "wr_oos_mean": res.get("wr_oos_mean", 0.0),
                "cagr_oos_prod": res.get("cagr_oos_prod", 0.0),
                "maxdd_oos_min": res.get("maxdd_oos_min", 0.0),
            }
            rows.append(row)
            if json_dir:
                with open(json_dir / f"{name}.json", "w") as f:
                    json.dump(res, f, ensure_ascii=False, indent=2)
            print(f"[OK] {fp}")
        except Exception as e:
            print(f"[FAIL] {fp}: {e}")

    if rows:
        df = pd.DataFrame(rows)
        df = df.sort_values(["tf", "sharpe_oos_mean", "pf_oos_mean"], ascending=[True, False, False])
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(args.out, index=False)
        print(f"[OK] Leaderboard -> {args.out}")
    else:
        print("[WARN] no successful results")

if __name__ == "__main__":
    main()
