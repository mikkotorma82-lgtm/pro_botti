#!/usr/bin/env python3
import json, sys
try:
    rows = json.load(open("data/broker_specs.json"))
except Exception:
    sys.exit(0)
for r in rows:
    if "error" in r: continue
    print(f"[SIZE] {r['symbol']} min={r['min_size']} step={r['step']} used={r.get('min_size')} currency={r['currency']} leverage={r.get('leverage')}")
