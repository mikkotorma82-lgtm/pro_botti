#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Env
if [ -f "./secrets.env" ]; then
  set -a; source ./secrets.env; set +a
fi

: "${SYMBOLS:?SYMBOLS must be set}"
: "${TFS:=15m,1h,4h}"
: "${HISTORY_DAYS:=365}"
: "${TOP_K:=5}"
: "${MIN_TRADES:=25}"

IFS=',' read -ra SYMS <<< "$SYMBOLS"
IFS=',' read -ra TFS_ARR <<< "$TFS"

for sym in "${SYMS[@]}"; do
  for tf in "${TFS_ARR[@]}"; do
    echo "[backfill] $sym $tf $HISTORY_DAYS"
    python scripts/backfill.py "$sym" "$tf" "$HISTORY_DAYS" || true
    echo "[train] $sym $tf"
    python scripts/train.py "$sym" "$tf" || true
  done
done

echo "[evaluate+select]"
python scripts/quick_evaluate_select.py --timeframes ${TFS//,/ } --lookback-days "${EVAL_LOOKBACK_DAYS:-365}" --top-k "$TOP_K" --min-trades "$MIN_TRADES"

# Restart live to pick up new active symbols (launch.sh overrides SYMBOLS from state file)
if systemctl is-active --quiet pro_botti; then
  echo "[notify] Restarting pro_botti"
  systemctl restart pro_botti || true
fi

echo "[auto_retrain] Done at $(date -Iseconds)"
