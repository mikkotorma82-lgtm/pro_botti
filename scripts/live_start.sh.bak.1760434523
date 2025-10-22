#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Lataa perusympäristö
if [ -f "./secrets.env" ]; then
  set -a; source ./secrets.env; set +a
fi

# Jos valinta on olemassa, yliaja SYMBOLS
if [ -f "state/active_symbols.json" ]; then
  export SYMBOLS="$(python - <<'PY'
import json
d=json.load(open("state/active_symbols.json"))
print(",".join(d.get("symbols", [])))
PY
)"
  echo "[live_start] Using active SYMBOLS=${SYMBOLS}"
fi

# Siirrä ajo varsinaiseen käynnistysskriptiin
exec /usr/bin/bash ./launch.sh
