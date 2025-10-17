#!/usr/bin/env python3
from __future__ import annotations
import os, json, time
from pathlib import Path
from typing import Dict, Any, List

STATE = Path(__file__).resolve().parents[1] / "state"
# UUSI: käytä aggregaattia jos olemassa
META_AGG = STATE / "agg_models_meta.json"
META_REG = META_AGG if META_AGG.exists() else (STATE / "models_meta.json")
SELECTED = STATE / "selected_universe.json"
ENV_OUT = STATE / "live_universe.env"

def load_meta() -> List[Dict[str, Any]]:
    if not META_REG.exists():
        raise SystemExit(f"[SELECT] missing {META_REG}")
    obj = json.loads(META_REG.read_text() or "{}")
    return obj.get("models", [])

def group_by_symbol(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    by: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        by.setdefault(r["symbol"], []).append(r)
    return by

def main():
    min_cvf = float(os.getenv("SELECT_MIN_CVPF", "1.20"))
    min_entries = int(os.getenv("SELECT_MIN_ENTRIES", "200"))
    max_tfs = int(os.getenv("SELECT_MAX_TFS_PER_SYMBOL", "2"))
    allow_15m = int(os.getenv("SELECT_ALLOW_15M", "0")) == 1
    prefer_set = [s.strip() for s in (os.getenv("SELECT_PREFERRED_TFS", "1h,4h")).split(",") if s.strip()]

    rows = load_meta()
    filt = []
    for r in rows:
        cvpf = float(r.get("cv_pf_score", r.get("auc_purged", 0.0)))
        ent = int(r.get("entries", 0))
        tf = r["tf"]
        if cvpf < min_cvf: 
            continue
        if ent < min_entries:
            continue
        if (tf == "15m") and not allow_15m:
            continue
        filt.append(r)

    def tf_rank(tf: str) -> int:
        try:
            return prefer_set.index(tf)
        except ValueError:
            return len(prefer_set)
    filt.sort(key=lambda r: (float(r.get("cv_pf_score", 0.0)), int(r.get("entries", 0)), -tf_rank(r["tf"])), reverse=True)

    by = group_by_symbol(filt)
    selected: List[Dict[str, Any]] = []
    for sym, lst in by.items():
        lst2 = sorted(lst, key=lambda x: (float(x.get("cv_pf_score",0.0)), int(x.get("entries",0))), reverse=True)
        selected.extend(lst2[:max_tfs])

    out = {
        "selected_at": int(time.time()),
        "rules": {
            "min_cvpf": min_cvf, "min_entries": min_entries,
            "max_tfs_per_symbol": max_tfs,
            "allow_15m": allow_15m, "preferred_tfs": prefer_set
        },
        "combos": [
            {
                "symbol": r["symbol"], "tf": r["tf"],
                "threshold": float(r.get("threshold", 0.6)),
                "cv_pf_score": float(r.get("cv_pf_score", 0.0)),
                "entries": int(r.get("entries", 0)),
                "asset_class": r.get("asset_class",""),
                "features": r.get("features", [])
            } for r in selected
        ]
    }
    tmp = SELECTED.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    os.replace(tmp, SELECTED)
    print(f"[SELECT] wrote {SELECTED} combos={len(out['combos'])}")

    # päivitettävä env out
    symbols = []
    tfs = set()
    for r in selected:
        if r["symbol"] not in symbols:
            symbols.append(r["symbol"])
        tfs.add(r["tf"])
    ENV_OUT.write_text(f"SYMBOLS='{','.join(symbols)}'\nLIVE_TFS='{','.join(sorted(tfs))}'\n")
    print(f"[SELECT] wrote {ENV_OUT}")

if __name__ == "__main__":
    main()
