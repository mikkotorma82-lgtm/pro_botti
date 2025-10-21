#!/usr/bin/env python3
from __future__ import annotations
import json, time, re
from pathlib import Path
from typing import Dict, Any, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state"
STATE.mkdir(parents=True, exist_ok=True)

PRO_CUR  = STATE / "models_pro.json"
META_CUR = STATE / "models_meta.json"
PRO_AGG  = STATE / "agg_models_pro.json"
META_AGG = STATE / "agg_models_meta.json"

def _safe_key(symbol: str, tf: str) -> str:
    k = f"{symbol}__{tf}"
    return re.sub(r"[^A-Za-z0-9_.-]", "", k)

def _load_json(p: Path, default: Dict[str, Any] | List[Any]):
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text() or (json.dumps(default)))
    except Exception:
        return default

def merge_from_current(kind: str) -> Tuple[int, int]:
    """
    kind: 'pro' tai 'meta'
    Lukee nykyisen rekisterin (models_*.json) ja upsertoi aggregaattiin (agg_models_*.json).
    Palauttaa (uuden aggregaatin model-count, lisätty/päivitetty -määrä).
    """
    now = int(time.time())
    if kind == "pro":
        cur = _load_json(PRO_CUR, {"models": []})
        agg = _load_json(PRO_AGG, {"models": []})
        def key(r): return (r.get("strategy") or "CONSENSUS", r.get("symbol"), r.get("tf"))
        by = { key(r): r for r in agg.get("models", []) }
        changed = 0
        for r in cur.get("models", []):
            if not r.get("symbol") or not r.get("tf"):
                continue
            k = key(r)
            # yhdistä kentät, säilytä uusin trained_at
            base = by.get(k, {})
            merged = { **base, **r }
            if "trained_at" not in merged:
                merged["trained_at"] = now
            by[k] = merged
            changed += 1
        out = {"models": list(by.values())}
        tmp = PRO_AGG.with_suffix(".tmp")
        tmp.write_text(json.dumps(out, ensure_ascii=False, indent=2))
        tmp.replace(PRO_AGG)
        return (len(out["models"]), changed)

    if kind == "meta":
        cur = _load_json(META_CUR, {"models": []})
        agg = _load_json(META_AGG, {"models": []})
        by = {}
        for r in agg.get("models", []):
            k = r.get("key") or _safe_key(r.get("symbol",""), r.get("tf",""))
            by[k] = r
        changed = 0
        for r in cur.get("models", []):
            sym = r.get("symbol"); tf = r.get("tf")
            if not sym or not tf:
                continue
            k = r.get("key") or _safe_key(sym, tf)
            nr = dict(r)
            nr["key"] = k
            nr["updated_at"] = now
            by[k] = { **by.get(k, {}), **nr }
            changed += 1
        out = {"models": list(by.values())}
        tmp = META_AGG.with_suffix(".tmp")
        tmp.write_text(json.dumps(out, ensure_ascii=False, indent=2))
        tmp.replace(META_AGG)
        return (len(out["models"]), changed)

    raise ValueError("kind must be 'pro' or 'meta'")
