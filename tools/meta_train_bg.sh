#!/usr/bin/env bash
set -euo pipefail
ROOT="/root/pro_botti"
PY="$ROOT/venv/bin/python"
LOG="$ROOT/logs/meta_train.$(date +%Y%m%dT%H%M%S).log"
mkdir -p "$ROOT/logs"

[ -f "$ROOT/secrets.env" ] && set -a && . "$ROOT/secrets.env" && set +a
[ -f "$ROOT/botti.env" ]   && set -a && . "$ROOT/botti.env"   && set +a

export META_PARALLEL="${META_PARALLEL:-2}"
export META_NOTIFY_SUMMARY="${META_NOTIFY_SUMMARY:-1}"
export META_NOTIFY_EACH="${META_NOTIFY_EACH:-0}"
export META_EXCHANGE_ID="${META_EXCHANGE_ID:-capitalcom}"
export META_TRAINER_PATH="${META_TRAINER_PATH:-tools.meta_ensemble:train_symbol_tf}"

nohup "$PY" -u -m tools.meta_train_job > "$LOG" 2>&1 < /dev/null &
echo "Started: $!  Log: $LOG"
