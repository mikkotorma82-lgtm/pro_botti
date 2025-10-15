#!/usr/bin/env python3
from __future__ import annotations
import os
from tools.capital_session import capital_rest_login, capital_get_bid_ask, capital_get_candles

def main():
    # Varmista, että envissä on CAPITAL_API_BASE, CAPITAL_API_KEY, CAPITAL_USERNAME, CAPITAL_PASSWORD
    s, base = capital_rest_login()
    print("[OK] logged in to:", base)

    for sym in ["US SPX 500", "EUR/USD", "GOLD", "AAPL", "BTC/USD"]:
        ba = capital_get_bid_ask(sym)
        print(f"{sym} bid/ask:", ba)
    # Kynttilät (esimerkki)
    rows = capital_get_candles("US SPX 500", "1h", 200)
    print("US SPX 500 1h candles rows:", len(rows) if rows is not None else 0)

if __name__ == "__main__":
    main()
