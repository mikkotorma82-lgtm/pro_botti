import os, sys, json, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.order_router import create_market_order

sym = sys.argv[1] if len(sys.argv)>1 else "BTCUSD"
side = sys.argv[2] if len(sys.argv)>2 else "buy"
qty = float(sys.argv[3]) if len(sys.argv)>3 else 0.001

res = create_market_order(sym, side, qty, dry_run=True)
print(json.dumps(res, indent=2))
