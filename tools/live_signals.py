from __future__ import annotations
import argparse, json, os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def infer_one(symbol: str, tf: str, limit_rows: int) -> dict:
    # Ajetaan saman projektin live_one modulina, jotta pidetään muistijalanjälki pienenä
    cmd = [
        sys.executable,
        "-m",
        "tools.live_one",
        "--symbol",
        symbol,
        "--tf",
        tf,
        "--limit_rows",
        str(limit_rows),
    ]
    out = subprocess.check_output(cmd, env=os.environ.copy())
    return json.loads(out.decode("utf-8"))


def apply_thresholds(item: dict, thr_buy: float, thr_sell: float) -> int:
    proba = item.get("proba", {})
    pbuy = float(proba.get("1", 0.0))
    psell = float(proba.get("-1", 0.0))
    if pbuy >= thr_buy:
        return 1
    if psell >= thr_sell:
        return -1
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", required=True)
    ap.add_argument("--tf", required=True)
    ap.add_argument("--limit_rows", type=int, default=2000)
    ap.add_argument("--thr_buy", type=float, default=0.10)
    ap.add_argument("--thr_sell", type=float, default=0.10)
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    # Rajoita säikeet ellei jo asetettu
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("NUMEXPR_MAX_THREADS", "1")

    out = []
    for s in args.symbols:
        try:
            item = infer_one(s, args.tf, args.limit_rows)
            item["signal"] = apply_thresholds(item, args.thr_buy, args.thr_sell)
            out.append(item)
        except Exception as e:
            out.append({"symbol": s, "tf": args.tf, "error": str(e)})

    print(json.dumps(out, ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()
