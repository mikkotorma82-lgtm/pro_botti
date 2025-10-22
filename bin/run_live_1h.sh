#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source venv/bin/activate
set -a; . botti.env; set +a
while true; do
  python3 - <<'PY'
from tools.trade_live import _load_universe
import json, subprocess
for s in _load_universe():
    p1=subprocess.Popen(["python3","-m","tools.live_one","--symbol",s,"--tf","1h","--limit_rows","2000"], stdout=subprocess.PIPE)
    p2=subprocess.Popen(["python3","-m","tools.risk_guard","--tf","1h"], stdin=p1.stdout, stdout=subprocess.PIPE)
    p1.stdout.close(); out,_=p2.communicate()
    try:
        d=json.loads(out.decode())
        if "units" in d and "side" in d:
            subprocess.run(["python3","-m","tools.trade_live"], input=json.dumps(d).encode(), check=False)
    except Exception:
        pass
PY
  sleep 300
done
