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

# Override SYMBOLS from state/active_symbols.json if present
if [ -f "state/active_symbols.json" ]; then
  ACTIVE_SYMBOLS="$( /root/pro_botti/venv/bin/python - <<\PY\nimport json,sys\ntry:\n    d=json.load(open(\"state/active_symbols.json\"))\n    syms=d.get(\"symbols\", [])\n    if not syms: sys.exit(2)\n    print(\",\".join(syms))\nexcept Exception:\n    sys.exit(1)\nPY )"
  if [ -n "$ACTIVE_SYMBOLS" ]; then
    export SYMBOLS="$ACTIVE_SYMBOLS"
    echo "[launch] Using active SYMBOLS=${SYMBOLS}"
  else
    echo "[launch] Warning: active_symbols.json empty/parse failed; using secrets.env SYMBOLS."
  fi
fi
