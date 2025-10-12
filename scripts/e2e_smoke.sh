#!/usr/bin/env bash
set -Eeuo pipefail
trap 'echo "[FAIL] rivillä $LINENO"; exit 1' ERR

cd /root/pro_botti

echo "[0] Stop palvelut"
systemctl stop pro-botti-health.timer 2>/dev/null || true
systemctl stop pro-botti.service || true

echo "[1] Prelive-check (paper smoke)"
./prelive_check.sh
test -s results/paper_smoke.json || { echo "[FAIL] paper_smoke.json puuttuu"; exit 1; }
echo "[OK] prelive_check + paper_smoke.json"

echo "[2] Käynnistä botti"
systemctl start pro-botti.service
sleep 4

echo "[3] Healthz & metrics"
curl -fsS http://127.0.0.1:8787/healthz | sed -e 's/^/[HEALTHZ] /'
curl -fsS http://127.0.0.1:9108/metrics | egrep -i "bot_uptime_seconds|bot_heartbeat_lag_seconds" | sed -e 's/^/[METRICS] /' || true

echo "[4] Livelokit (lataukset/signalit)"
journalctl -u pro-botti.service --since "3 min ago" --no-pager | \
egrep -i "loaded pro_|signal|decision|order|trade|position|BUY|SELL" || echo "[INFO] ei signaaleja vielä"

echo "[5] Apufunktiot ilman sivuvaikutuksia (ld_utils)"
python3 - <<'PY'
from tools.ld_utils import should_send_daily_digest, rank_symbols_by_edge, scale_risk_from_meta
now=1234567890
print("[UTIL] digest:", should_send_daily_digest(None, now), should_send_daily_digest(now-60, now, 300), should_send_daily_digest(now-600, now, 300))
print("[UTIL] rank:",  rank_symbols_by_edge({"BTC":{"15m":0.6,"1h":0.5},"ETH":{"15m":0.7}}, 1))
print("[UTIL] risk:",  scale_risk_from_meta({"volatility":1.8,"max_drawdown":0.35,"max_position_usdt":150}, 200))
PY

echo "[6] Jatkuva valvonta takaisin päälle"
systemctl enable --now pro-botti-health.timer 2>/dev/null || true

echo "[DONE] E2E paper-savutus valmis"
