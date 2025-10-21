#!/usr/bin/env python3
from __future__ import annotations
import os, json
from pathlib import Path
from typing import List, Dict, Any

from tools.capital_session import capital_get_candles_df
from tools.consensus_engine import consensus_signal

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "state"
REG_PATH = STATE_DIR / "models_pro.json"

def _read_symbols() -> List[str]:
    raw = os.getenv("TRADE_SYMBOLS") or os.getenv("CAPITAL_SYMBOLS") or ""
    syms = [s.strip() for s in raw.split(",") if s.strip()]
    return syms or ["US SPX 500","EUR/USD","GOLD","AAPL","BTC/USD"]

def _load_registry() -> Dict[str, Any]:
    if not REG_PATH.exists():
        return {"models": []}
    return json.loads(REG_PATH.read_text())

def _find_model(reg: Dict[str, Any], symbol: str, tf: str) -> Dict[str, Any] | None:
    rows = [m for m in reg.get("models", []) if m.get("symbol")==symbol and m.get("tf")==tf]
    if not rows:
        return None
    rows.sort(key=lambda r: int(r.get("trained_at", 0)), reverse=True)
    return rows[0]

def main():
    tfs = [s.strip() for s in (os.getenv("LIVE_TFS") or "1h").split(",") if s.strip()]
    reg = _load_registry()
    for sym in _read_symbols():
        for tf in tfs:
            m = _find_model(reg, sym, tf)
            if not m:
                print(f"{sym} {tf}: HOLD (no model)")
                continue
            cfg = m.get("config") or {}
            df = capital_get_candles_df(sym, tf, total_limit=600)
            if df.empty:
                print(f"{sym} {tf}: HOLD (no data)")
                continue
            sig = consensus_signal(df, cfg)
            last = int(sig[-1]) if len(sig)>0 else 0
            act = "BUY" if last>0 else ("SELL" if last<0 else "HOLD")
            print(f"{sym} {tf}: {act} cfg={cfg['params']} thr={cfg['threshold']}")

if __name__ == "__main__":
    main()
