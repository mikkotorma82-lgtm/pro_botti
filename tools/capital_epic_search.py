#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from tools.capital_session import capital_market_search

def main():
    ap = argparse.ArgumentParser(description="Search Capital markets by display name to find EPICs")
    ap.add_argument("--q", required=True, help="Search term, e.g. 'US SPX 500', 'EUR/USD', 'GOLD', 'AAPL'")
    ap.add_argument("--limit", type=int, default=25)
    args = ap.parse_args()

    hits = capital_market_search(args.q, limit=args.limit)
    if not hits:
        print("No results.")
        return
    for h in hits:
        print(json.dumps(
            {
                "epic": h.get("epic"),
                "name": h.get("instrumentName"),
                "raw_keys": list((h.get("raw") or {}).keys()),
            },
            ensure_ascii=False
        ))

if __name__ == "__main__":
    main()
