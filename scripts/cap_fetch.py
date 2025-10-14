#!/usr/bin/env python3
from __future__ import annotations
import argparse, sys, time
from tools.capital_api import CapitalClient, CapitalError

def main():
    ap = argparse.ArgumentParser(description="Fetch OHLC candles from Capital.com LIVE API")
    ap.add_argument("--symbol", required=True, help="Capital instrument symbol, esim: US500, AAPL, EUR/USD, GOLD, BTC/USD")
    ap.add_argument("--tf", required=True, help="15m | 1h | 4h | 1d ... (mapped -> M15/H1/H4/D1)")
    ap.add_argument("--from", dest="from_iso", default=None, help="ISO8601 start (e.g. 2025-09-01T00:00:00Z)")
    ap.add_argument("--to", dest="to_iso", default=None, help="ISO8601 end (e.g. 2025-10-14T00:00:00Z)")
    ap.add_argument("--limit", type=int, default=200, help="max rows (server permitting)")
    ap.add_argument("--head", type=int, default=5, help="print first N rows")
    args = ap.parse_args()

    try:
        cli = CapitalClient()
        cli.login()
        me = cli.whoami()
        print("[ok] logged in; whoami keys:", list(me.keys()))

        df = cli.candles(symbol=args.symbol, resolution=args.tf, from_iso=args.from_iso, to_iso=args.to_iso, limit=args.limit)
        print(f"[ok] candles: rows={len(df)} cols={list(df.columns)}")
        print(df.head(args.head).to_string(index=False))
    except CapitalError as e:
        print(f"[fail] capital api: {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"[fail] unexpected: {e}", file=sys.stderr)
        sys.exit(3)

if __name__ == "__main__":
    main()
