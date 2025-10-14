#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -f "./secrets.env" ]; then set -a; source ./secrets.env; set +a; fi

SYMS_SPACE="${SYMBOLS//,/ }"
TFS_SPACE="${TFS:-15m,1h,4h}"; TFS_SPACE="${TFS_SPACE//,/ }"
LOOKBACK="${EVAL_LOOKBACK_DAYS:-365}"
TOPK="${TOP_K:-5}"
MINTR="${MIN_TRADES:-10}"

source venv/bin/activate || true
pip install -q --upgrade pip
pip install -q ccxt yfinance pandas numpy scikit-learn joblib

echo "[run] train_all_models for: ${SYMS_SPACE} @ ${TFS_SPACE}"
python scripts/train_all_models.py --symbols ${SYMS_SPACE} --timeframes ${TFS_SPACE} --lookback-days "${LOOKBACK}"

echo "[run] model_evaluate_select (Top-${TOPK})"
python scripts/model_evaluate_select.py --symbols ${SYMS_SPACE} --timeframes ${TFS_SPACE} --lookback-days "${LOOKBACK}" --top-k "${TOPK}" --min-trades "${MINTR}"

echo "[run] restart live"
systemctl restart pro_botti || true
echo "[run] done"
