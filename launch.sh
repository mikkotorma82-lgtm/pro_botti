#!/usr/bin/env bash
set -euo pipefail
ROOT=${ROOT:-/root/pro_botti}
cd "$ROOT"

if [ -f "$ROOT/botti.env" ]; then
  set -a
  source "$ROOT/botti.env"
  set +a
fi

if [ -f "$ROOT/config/active_symbols.txt" ]; then
  SYMBOLS="$(tr -d '\r' < "$ROOT/config/active_symbols.txt" | awk 'NF' | paste -sd, -)"
else
  SYMBOLS="EURUSD"
fi
export SYMBOLS

echo "[$(date -Iseconds)] [INFO] käynnistyy: SYMBOLS=[${SYMBOLS}]"

exec /usr/bin/env python3 -m tools.live_daemon
