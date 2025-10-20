#!/usr/bin/env bash
set -euo pipefail
ROOT="/root/pro_botti"
PY="$ROOT/venv/bin/python"

# Load env
[ -f "$ROOT/secrets.env" ] && set -a && . "$ROOT/secrets.env" && set +a
[ -f "$ROOT/botti.env" ]   && set -a && . "$ROOT/botti.env"   && set +a

# Gentle defaults
export META_PARALLEL="${META_PARALLEL:-2}"
export META_NOTIFY_SUMMARY="${META_NOTIFY_SUMMARY:-1}"
export META_NOTIFY_EACH="${META_NOTIFY_EACH:-0}"
export META_EXCHANGE_ID="${META_EXCHANGE_ID:-capitalcom}"
export META_TRAINER_PATH="${META_TRAINER_PATH:-tools.meta_ensemble:train_symbol_tf}"

# Guard: if returns 100 (fresh), skip but exit 0
if "$ROOT/tools/train_bundle_guard.sh"; then
  :
else
  code=$?
  if [ "$code" -eq 100 ]; then
    echo "[META-JOB] models fresh -> skip training"
    exit 0
  else
    echo "[META-JOB] guard failed: $code" >&2
    exit "$code"
  fi
fi

exec "$PY" -u -m tools.meta_train_job
