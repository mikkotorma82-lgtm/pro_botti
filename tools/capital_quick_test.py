#!/usr/bin/env python3
from __future__ import annotations
from tools.capital_session import capital_rest_login, capital_get_bid_ask, capital_get_candles, _resolve_epic

def main():
    s, base = capital_rest_login()
    print("[OK] logged in to:", base)

    syms = ["US SPX 500", "EUR/USD", "GOLD", "AAPL", "BTC/USD"]
    for sym in syms:
        epic = _resolve_epic(sym)
        ba = capital_get_bid_ask(sym)
        print(f"{sym} -> EPIC={epic} bid/ask:", ba)

    rows = capital_get_candles("US SPX 500", "1h", 200)
    print("US SPX 500 1h candles rows:", len(rows) if rows is not None else 0)

if __name__ == "__main__":
    main()
