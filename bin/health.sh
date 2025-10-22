#!/usr/bin/env bash
set -euo pipefail
ROOT=/root/pro_botti
set -a; [ -f "$ROOT/botti.env" ] && source "$ROOT/botti.env"; set +a

mask() {
  v="${1-}"                 # älä kaadu jos arg puuttuu
  [ -z "$v" ] && { echo ""; return; }
  l=${#v}
  [ "$l" -le 4 ] && { echo "****"; return; }
  echo "${v:0:2}****${v: -2}"
}

echo "[HEALTH] ENV:"
echo "  CAPITAL_ENV=$(echo "${CAPITAL_ENV:-}")"
echo "  CAPITAL_API_KEY=$(mask "${CAPITAL_API_KEY:-}")"
echo "  CAPITAL_LOGIN=$(mask "${CAPITAL_LOGIN:-}")"
echo "  TRADE_LIVE=${TRADE_LIVE:-0}"
echo "  SIZE_DEFAULT=${SIZE_DEFAULT:-1}"

echo "[HEALTH] Capital quick selftest:"
"$ROOT/venv/bin/python" "$ROOT/capital_api.py" || true

echo "[HEALTH] Symbols (parsed):"
tr -d '\r' < "$ROOT/config/active_symbols.txt" | sed -E 's/#.*$//' | awk 'NF' | paste -sd, -
