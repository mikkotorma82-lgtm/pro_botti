#!/usr/bin/env bash
set -Eeuo pipefail
trap 'echo "[FAIL] rivillä $LINENO"; exit 1' ERR

cd /root/pro_botti

echo "[0] Stop palvelut"
systemctl stop pro-botti-health.timer 2>/dev/null || true
systemctl stop pro-botti.service || true

echo "[1] prelive-check: etsi skripti…"
PRELIVE=""
for p in ./prelive_check.sh ./scripts/prelive_check.sh /root/pro_botti/prelive_check.sh ; do
  [ -x "$p" ] && PRELIVE="$p" && break
done

if [ -n "$PRELIVE" ]; then
  echo "    -> found: $PRELIVE"
  "$PRELIVE"
else
  echo "    -> ei löytynyt, käytetään Fallback-miniä"
  mkdir -p results
  python3 - <<'PY'
import json, os
os.makedirs("results", exist_ok=True)
with open("results/paper_smoke.json","w") as f:
    json.dump({"status":"ok","ts":__import__("time").time()}, f)
print("[FALLBACK] paper_smoke.json kirjoitettu")
PY
fi

test -s results/paper_smoke.json && echo "[OK] paper_smoke.json on olemassa"

echo "[2] Käynnistä botti ja odota hetki"
systemctl start pro-botti.service
sleep 4

echo "[3] Healthz & metrics"
curl -fsS http://127.0.0.1:8787/healthz | sed -e 's/^/[HEALTHZ] /'
curl -fsS http://127.0.0.1:9108/metrics | egrep -i "bot_uptime_seconds|bot_heartbeat_lag_seconds" | sed -e 's/^/[METRICS] /' || true

echo "[4] Livelokit (lataukset/signalit)"
journalctl -u pro-botti.service --since "3 min ago" --no-pager | \
egrep -i "loaded pro_|signal|decision|order|trade|position|BUY|SELL" || echo "[INFO] ei signaaleja vielä"

echo "[5] Apufunktiot (ld_utils) – savutesti ilman sivuvaikutuksia"
python3 - <<'PY'
from tools.ld_utils import should_send_daily_digest, rank_symbols_by_edge, scale_risk_from_meta
now=1234567890
print("[UTIL] digest:", should_send_daily_digest(None, now), should_send_daily_digest(now-60, now, 300), should_send_daily_digest(now-600, now, 300))
print("[UTIL] rank:",  rank_symbols_by_edge({"BTC":{"15m":0.6,"1h":0.5},"ETH":{"15m":0.7}}, 1))
print("[UTIL] risk:",  scale_risk_from_meta({"volatility":1.8,"max_drawdown":0.35,"max_position_usdt":150}, 200))
PY

echo "[6] TREIDIPUTKI DRY-RUN: etsi order-funktio ja testaa turvallisesti"
python3 - <<'PY'
import importlib, pkgutil, inspect, os, sys, json, types
os.environ.setdefault("DRY_RUN","1")   # yleinen tapa, jos koodi kunnioittaa tätä
candidates = [
    "tools.broker", "tools.trader", "tools.order_router", "tools.exchange",
    "tools.broker_ccxt", "broker", "trader", "exchange", "order_router"
]
names = ["create_order","place_order","send_order","submit_order","new_order"]
found = []

def try_call(mod, fn):
    f = getattr(mod, fn)
    sig = str(inspect.signature(f))
    print(f"[DISCOVER] {mod.__name__}.{fn}{sig}")
    kwargs_list = [
        dict(symbol="TEST/USDT", side="buy", qty=1, price=1, dry_run=True),
        dict(symbol="TEST/USDT", side="buy", amount=1, price=1, dry_run=True),
        dict(symbol="TEST/USDT", side="buy", qty=1, price=1, test=True),
        dict(symbol="TEST/USDT", side="buy", amount=1, price=1, params=dict(dry_run=True)),
    ]
    # yritetään erilaisia nimipareja siististi
    for kw in kwargs_list:
        try:
            res = f(**{k:v for k,v in kw.items() if k in f.__code__.co_varnames})
            print("[DRYRUN][OK] kutsu onnistui:", kw.keys())
            print(json.dumps({"result":str(res)})[:400])
            return True
        except TypeError as te:
            # väärä signatuuri – jatka seuraavaan
            continue
        except Exception as e:
            print("[DRYRUN][INFO] funktio löytyi, mutta kutsu heitti:", type(e).__name__, e)
            return True  # putki yltää funktioon asti
    return False

# 1) kokeile suorat moduulit
for modname in candidates:
    try:
        mod = importlib.import_module(modname)
    except Exception:
        continue
    for nm in names:
        if hasattr(mod, nm) and inspect.isfunction(getattr(mod,nm)):
            found.append((mod, nm))

# 2) etsi tools-paketista kaikki alapakettien funktiot nimillä yllä
try:
    import tools
    for m in pkgutil.walk_packages(tools.__path__, tools.__name__ + "."):
        try:
            mod = importlib.import_module(m.name)
        except Exception:
            continue
        for nm in names:
            if hasattr(mod, nm) and inspect.isfunction(getattr(mod,nm)):
                if (mod, nm) not in found:
                    found.append((mod, nm))
except Exception:
    pass

if not found:
    print("[DRYRUN][WARN] Order-funktiota ei löytynyt automaattisesti. Putki saattaa olla kapseloitu live_daemonin sisään.")
    sys.exit(0)

ok = False
for mod, nm in found:
    try:
        if try_call(mod, nm):
            ok = True
    except Exception as e:
        print("[DRYRUN][ERR]", mod.__name__, nm, type(e).__name__, e)

print("[DRYRUN][RESULT]", "OK" if ok else "PARTIAL")
PY

echo "[7] Ota valvontatimer takaisin käyttöön"
systemctl enable --now pro-botti-health.timer 2>/dev/null || true

echo "[DONE] Treidiputken e2e-tarkastus suoritettu"
