#!/usr/bin/env python3
from __future__ import annotations
import json, time
from pathlib import Path
from typing import Dict, Any, Tuple

STATE = Path(__file__).resolve().parents[1] / "state"
STATE.mkdir(parents=True, exist_ok=True)
REG = STATE / "models_pro.json"
FREQ = STATE / "trade_freq_stats.json"  # { "targets":{"all":10,"US SPX 500__15m":3}, "counts":{key: {"ts":epoch, "n":int}} }

def _load(p: Path, default: Any) -> Any:
    if not p.exists(): return default
    try: return json.loads(p.read_text())
    except Exception: return default

def _save(p: Path, obj: Any) -> None:
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2))

def record_trade(symbol: str, tf: str) -> None:
    data = _load(FREQ, {"targets":{"all":10.0},"counts":{}})
    key = f"{symbol}__{tf}"
    c = data["counts"].get(key, {"ts": int(time.time()), "n": 0})
    # reset daily
    now = int(time.time()); day = now // 86400; day_prev = int(c.get("ts", 0)) // 86400
    if day != day_prev: c = {"ts": now, "n": 0}
    c["ts"] = now; c["n"] = int(c.get("n", 0)) + 1
    data["counts"][key] = c
    _save(FREQ, data)

def calibrate_thresholds(k: float = 0.05, min_thr: float = 0.1, max_thr: float = 0.9) -> int:
    """
    Pienin askelin säädä per-symboli+TF kynnystä kohti tavoitetta (bandit-tyyppisesti).
    k = säätökerroin / päivä
    Palauttaa muutettujen mallien määrän.
    """
    reg = _load(REG, {"models":[]})
    freq = _load(FREQ, {"targets":{"all":10.0},"counts":{}})
    targets: Dict[str, float] = freq.get("targets", {"all":10.0})
    changed = 0
    for m in reg.get("models", []):
        sym, tf = m.get("symbol"), m.get("tf")
        key = f"{sym}__{tf}"
        target = float(targets.get(key, targets.get("all", 10.0)))
        count = float(freq.get("counts", {}).get(key, {}).get("n", 0))
        thr = float(m.get("config", {}).get("threshold", 0.5))
        # Jos liian vähän kauppoja -> laske kynnystä; jos liikaa -> nosta
        err = (target - count) / max(target, 1.0)
        new_thr = max(min_thr, min(max_thr, thr - k * err))
        if abs(new_thr - thr) >= 1e-6:
            m["config"]["threshold"] = new_thr
            m["trained_at"] = int(time.time())
            changed += 1
    if changed:
        _save(REG, reg)
    return changed
