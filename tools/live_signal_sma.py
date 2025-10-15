#!/usr/bin/env python3
from __future__ import annotations
import os
from typing import List

from tools.strategy_sma import next_action

def _read_symbols() -> List[str]:
    raw = os.getenv("TRADE_SYMBOLS") or os.getenv("CAPITAL_SYMBOLS") or ""
    syms = [s.strip() for s in raw.split(",") if s.strip()]
    if not syms:
        syms = ["US SPX 500", "EUR/USD", "GOLD", "AAPL", "BTC/USD"]
    return syms

def main():
    tfs = [s.strip() for s in (os.getenv("LIVE_TFS") or "1h").split(",") if s.strip()]
    for sym in _read_symbols():
        for tf in tfs:
            sig, n = next_action(sym, tf)
            print(f"{sym} {tf}: {sig} (n={n})")

if __name__ == "__main__":
    main()
