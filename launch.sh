#!/usr/bin/env bash
set -euo pipefail

ROOT=${ROOT:-/root/pro_botti}
cd "$ROOT"

# Lataa ympäristö
if [ -f "$ROOT/botti.env" ]; then
  set -a
  source "$ROOT/botti.env"
  set +a
fi
# Tuetaan myös .env jos sellainen on
if [ -f "$ROOT/.env" ]; then
  set -a
  source "$ROOT/.env"
  set +a
fi

# Varmista venv Python
VENV_PY="$ROOT/venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
  # fallback järjestelmän python3:een jos venv puuttuu
  VENV_PY="$(command -v python3 || true)"
fi

# SYMBOLS prioriteetti:
# 1) jos SYMBOLS on jo asetettu (esim. live_start.sh), älä koske
# 2) state/active_symbols.json (Top-5 valinta)
# 3) config/active_symbols.txt (rivi/symboli -> yhdistetään pilkuilla)
# 4) fallback
if [ -z "${SYMBOLS:-}" ]; then
  if [ -f "$ROOT/state/active_symbols.json" ] && [ -n "${VENV_PY:-}" ]; then
    ACTIVE="$("$VENV_PY" - <<'PY' || true
import json,sys
try:
    d=json.load(open("state/active_symbols.json"))
    syms=d.get("symbols", [])
    if not syms:
        sys.exit(2)
    print(",".join(syms))
except Exception:
    sys.exit(1)
PY
)"
    if [ -n "$ACTIVE" ]; then
      SYMBOLS="$ACTIVE"
    fi
  fi
fi

if [ -z "${SYMBOLS:-}" ]; then
  if [ -s "$ROOT/config/active_symbols.txt" ]; then
    SYMBOLS="$(tr -d '\r' < "$ROOT/config/active_symbols.txt" | awk 'NF' | paste -sd, -)"
  else
    # Fallback
    SYMBOLS="EURUSD,GBPUSD,US500,US100,BTCUSD,ETHUSD"
  fi
fi
export SYMBOLS

echo "[$(date -Iseconds)] [INFO] käynnistyy: SYMBOLS=[${SYMBOLS}] TFS=[${TFS:-15m,1h,4h}]"

# Aja daemon venvin pythonilla jos mahdollista
if [ -n "${VENV_PY:-}" ]; then
  exec "$VENV_PY" -u -m tools.live_daemon
else
  exec /usr/bin/env python3 -u -m tools.live_daemon
fi
