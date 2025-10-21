#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple
from tools.symbol_resolver import read_symbols

STATE = Path(__file__).resolve().parents[1] / "state"
STATE.mkdir(parents=True, exist_ok=True)
PRO_REG  = STATE / "models_pro.json"
META_REG = STATE / "models_meta.json"
OUT_JSON = STATE / "missing_models.json"

def load_reg(p: Path) -> Dict[str, Any]:
    if not p.exists():
        return {"models": []}
    try:
        return json.loads(p.read_text() or '{"models":[]}')
    except Exception:
        return {"models": []}

def main():
    syms = read_symbols()
    tfs = ["15m","1h","4h"]
    pro = load_reg(PRO_REG)
    meta = load_reg(META_REG)
    pro_set  = {(m.get("symbol"), m.get("tf")) for m in pro.get("models", []) if m.get("strategy") == "CONSENSUS"}
    meta_set = {(m.get("symbol"), m.get("tf")) for m in meta.get("models", [])}
    missing_pro, missing_meta, both = [], [], []

    for s in syms:
        for tf in tfs:
            need_pro  = (s, tf) not in pro_set
            need_meta = (s, tf) not in meta_set
            if need_pro and need_meta:
                both.append({"symbol": s, "tf": tf})
            elif need_pro:
                missing_pro.append({"symbol": s, "tf": tf})
            elif need_meta:
                missing_meta.append({"symbol": s, "tf": tf})

    res = {
        "symbols_in_config": len(syms),
        "tfs": tfs,
        "missing_pro": missing_pro,
        "missing_meta": missing_meta,
        "missing_both": both,
        "missing_total": len(missing_pro) + len(missing_meta) + len(both)
    }
    tmp = OUT_JSON.with_suffix(".tmp")
    tmp.write_text(json.dumps(res, ensure_ascii=False, indent=2))
    tmp.replace(OUT_JSON)

    print(f"Symbols in config: {len(syms)}; combos={len(syms)*len(tfs)}")
    print(f"Missing PRO only: {len(missing_pro)}  | Missing META only: {len(missing_meta)}  | Missing BOTH: {len(both)}")
    for bucket, lst in (("BOTH", both), ("PRO", missing_pro), ("META", missing_meta)):
        for r in lst[:90]:
            print(f"[{bucket}] {r['symbol']} {r['tf']}")

if __name__ == "__main__":
    main()
