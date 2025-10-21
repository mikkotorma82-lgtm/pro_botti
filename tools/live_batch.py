from __future__ import annotations
import argparse, subprocess, os


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", required=True)
    ap.add_argument("--symbols", nargs="+", required=True)
    ap.add_argument("--limit_rows", type=int, default=2000)
    ap.add_argument("--thr_buy", type=float, default=0.10)
    ap.add_argument("--thr_sell", type=float, default=0.10)
    args = ap.parse_args()

    env = os.environ.copy()
    env.setdefault("OMP_NUM_THREADS", "1")
    env.setdefault("MKL_NUM_THREADS", "1")
    env.setdefault("OPENBLAS_NUM_THREADS", "1")
    env.setdefault("NUMEXPR_MAX_THREADS", "1")

    for s in args.symbols:
        print(f"[i] {s}")
        p = subprocess.run(
            [
                "python3",
                "-m",
                "tools.live_one",
                "--symbol",
                s,
                "--tf",
                args.tf,
                "--limit_rows",
                str(args.limit_rows),
                "--thr_buy",
                str(args.thr_buy),
                "--thr_sell",
                str(args.thr_sell),
            ],
            env=env,
            capture_output=True,
            text=True,
        )
        if p.stderr:
            print(f"[ERR {s}] {p.stderr.strip()}")
        print(f"[OUT {s}] {p.stdout.strip()}")


if __name__ == "__main__":
    main()
