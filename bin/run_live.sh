#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source venv/bin/activate
set -a; . botti.env; set +a

while true; do
  python3 - <<'PY'
from tools._dotenv import load_dotenv; load_dotenv()
from tools.trade_live import _load_universe
import json, os, subprocess, sys

SYMS = _load_universe()
for s in SYMS:
    p1 = subprocess.Popen(["python3","-m","tools.live_one","--symbol",s,"--tf","1h","--limit_rows","2000"], stdout=subprocess.PIPE)
    p2 = subprocess.Popen(["python3","-m","tools.risk_guard","--tf","1h"], stdin=p1.stdout, stdout=subprocess.PIPE)
    p1.stdout.close()
    out, _ = p2.communicate()
    # vain jos tuli täysi signaali
    try:
        d=json.loads(out.decode())
        if "units" in d and "side" in d:
            p3 = subprocess.Popen(["python3","-m","tools.trade_live"], stdin=subprocess.PIPE)
            p3.communicate(input=json.dumps(d).encode())
    except Exception:
        pass
PY
  sleep 60
done
