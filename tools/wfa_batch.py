from __future__ import annotations
import csv, json
from pathlib import Path
from tools.wfa import wfa_one
from tools.backfill import load_universe

OUT = Path("data/metrics")
OUT.mkdir(parents=True, exist_ok=True)


def run_all(tf: str):
    syms = load_universe()
    rows = []
    for s in syms:
        r = wfa_one(s, tf)
        print(json.dumps(r, ensure_ascii=False))
        if r.get("ok"):
            rows.append(r)
    out = OUT / f"metrics_{tf}.csv"
    with out.open("w", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["symbol", "tf", "roi", "sharpe", "trades", "maxdd", "ok"]
        )
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return out


def aggregate():
    files = list(OUT.glob("metrics_*.csv"))
    rows = []
    for p in files:
        import csv

        with p.open() as f:
            r = csv.DictReader(f)
            rows += list(r)
    out = OUT / "latest_metrics.csv"
    with out.open("w", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["symbol", "tf", "roi", "sharpe", "trades", "maxdd"]
        )
        w.writeheader()
        for r in rows:
            w.writerow(
                {
                    "symbol": r["symbol"],
                    "tf": r["tf"],
                    "roi": r["roi"],
                    "sharpe": r["sharpe"],
                    "trades": r["trades"],
                    "maxdd": r["maxdd"],
                }
            )
    return out


if __name__ == "__main__":
    for tf in ("15m", "1h", "4h"):
        run_all(tf)
    p = aggregate()
    print(json.dumps({"ok": True, "output": str(p)}, ensure_ascii=False))
