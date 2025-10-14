#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Lataa perusympäristö
if [ -f "./secrets.env" ]; then
  set -a; source ./secrets.env; set +a
fi

# Käytä venvin Pythonia tai fallback
VENV_PY="/root/pro_botti/venv/bin/python"
PYTHON=""
if [ -x "$VENV_PY" ]; then
  PYTHON="$VENV_PY"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON="python"
else
  PYTHON=""
fi

# Jos valinta on olemassa ja Python löytyy, yliaja SYMBOLS
if [ -f "state/active_symbols.json" ] && [ -n "${PYTHON}" ]; then
  if ACTIVE="$("$PYTHON" - <<'PY'
import json,sys
try:
    d=json.load(open("state/active_symbols.json"))
    syms = d.get("symbols", [])
    if not syms:
        sys.exit(2)
    print(",".join(syms))
except Exception:
    sys.exit(1)
PY
)"; then
    export SYMBOLS="${ACTIVE}"
    echo "[live_start] Using active SYMBOLS=${SYMBOLS}"
  else
    echo "[live_start] Warning: failed to parse state/active_symbols.json or empty symbols; using secrets.env SYMBOLS."
  fi
else
  if [ ! -f "state/active_symbols.json" ]; then
    echo "[live_start] No state/active_symbols.json; using secrets.env SYMBOLS."
  else
    echo "[live_start] No Python interpreter found to parse state/active_symbols.json; using secrets.env SYMBOLS."
  fi
fi

# Käynnistä varsinainen launch
exec /usr/bin/bash ./launch.sh
