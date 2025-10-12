#!/usr/bin/env bash
set -euo pipefail

ROOT="/root/pro_botti"
VENV_PY="$ROOT/venv/bin/python"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"

export PYTHONUNBUFFERED=1

# Lataa env (molemmat sallittuja)
if [ -f "$ROOT/botti.env" ]; then set -a; . "$ROOT/botti.env"; set +a; fi
if [ -f "$ROOT/.env" ]; then set -a; . "$ROOT/.env"; set +a; fi

# Kokoa SYMBOLS jos ei tule envistä
if [ -z "${SYMBOLS:-}" ]; then
  if [ -s "$ROOT/config/active_symbols.txt" ]; then
    SYMBOLS="$(tr -d '\r' < "$ROOT/config/active_symbols.txt" | awk 'NF' | paste -sd, -)"
  else
    SYMBOLS="EURUSD,USDJPY,GBPUSD,XAUUSD,BTCUSDT"
  fi
fi
export SYMBOLS

echo "[$(date -Iseconds)] [INFO] käynnistyy: SYMBOLS=[${SYMBOLS}] TFS=[${TFS:-15m,1h,4h}]"

# Aja daemon venvin pythonilla
exec "$VENV_PY" -u -m tools.live_daemon
