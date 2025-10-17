#!/usr/bin/env python3
from __future__ import annotations
import os, json, subprocess, shlex, time
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state"
MISS  = STATE / "missing_models.json"

def load_missing() -> Dict[str, Any]:
    if not MISS.exists():
        raise SystemExit("missing_models.json puuttuu – aja ensin: python -m tools.audit_missing")
    return json.loads(MISS.read_text() or "{}")

def plan_runs(missing: Dict[str, Any]) -> List[Tuple[str, Set[str]]]:
    # Palauta lista (symboli, tf_joukko), joille pitää ajaa PRO+META
    buckets = ["missing_both", "missing_pro", "missing_meta"]
    per_symbol: Dict[str, Set[str]] = {}
    for b in buckets:
        for r in missing.get(b, []):
            per_symbol.setdefault(r["symbol"], set()).add(r["tf"])
    return sorted([(s, tfs) for s, tfs in per_symbol.items()], key=lambda x: x[0])

def run(cmd: str, extra_env: Dict[str,str] = {}) -> int:
    env = os.environ.copy()
    env.update(extra_env)
    print(f"[RUN] {cmd}")
    return subprocess.call(cmd, shell=True, cwd=str(ROOT), env=env)

def main():
    missing = load_missing()
    runs = plan_runs(missing)
    if not runs:
        print("[TRAIN-MISSING] ei puuttuvia – valmis")
        return
    print(f"[TRAIN-MISSING] symbols={len(runs)}")
    for sym, tfs in runs:
        tfs_csv = ",".join(sorted(tfs))
        # Aja PRO ja META vain tälle symbolille ja puuttuviin TF:iin
        env = {
            "SYMBOLS": sym,
            "TRAIN_TFS": tfs_csv,
            "PYTHONUNBUFFERED": "1"
        }
        rc1 = run("./venv/bin/python -m tools.train_wfa_pro", env)
        rc2 = run("./venv/bin/python -m tools.train_meta", env)
        print(f"[TRAIN-MISSING] {sym} tfs={tfs_csv} -> PRO rc={rc1} META rc={rc2}")
        time.sleep(0.2)
    print("[TRAIN-MISSING] done")

if __name__ == "__main__":
    main()
