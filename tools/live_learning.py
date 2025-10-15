#!/usr/bin/env python3
from __future__ import annotations
import json, time, os
from pathlib import Path
from typing import Dict, Any

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
REG_IN  = STATE_DIR / "models_pro.json"
FBK_IN  = STATE_DIR / "live_feedback.json"   # {entries:[{symbol,tf,date,return,config}]}
REG_OUT = STATE_DIR / "models_pro.json"      # ylikirjoitetaan uusilla painotuksilla (varovasti)

def _load_json(p: Path, default: Any) -> Any:
    if not p.exists():
        return default
    return json.loads(p.read_text())

def _save_json(p: Path, obj: Any) -> None:
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2))

def main():
    reg = _load_json(REG_IN, {"models": []})
    fb  = _load_json(FBK_IN, {"entries": []})
    if not fb.get("entries"):
        print("[INFO] no feedback entries")
        return

    # Yksinkertainen bandit-tyyppinen päivitys:
    # jos palautus > 0 -> kevennä thresholdia hieman (-0.05), jos < 0 -> nosta hieman (+0.05).
    changed = 0
    for e in fb["entries"]:
        sym, tf, ret = e.get("symbol"), e.get("tf"), float(e.get("return", 0.0))
        cfg = e.get("config") or {}
        for m in reg.get("models", []):
            if m.get("symbol")==sym and m.get("tf")==tf and m.get("strategy")=="CONSENSUS":
                thr = float(m["config"].get("threshold", 0.5))
                adj = -0.05 if ret>0 else (0.05 if ret<0 else 0.0)
                new_thr = min(0.9, max(0.1, thr + adj))
                m["config"]["threshold"] = new_thr
                m["trained_at"] = int(time.time())  # päivitä aikaleima
                changed += 1
                break

    if changed:
        _save_json(REG_OUT, reg)
        print(f"[OK] updated registry thresholds on {changed} model(s)")
    else:
        print("[INFO] nothing updated")

if __name__ == "__main__":
    main()
