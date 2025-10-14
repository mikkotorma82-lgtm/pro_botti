#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Env (valinnainen)
if [ -f "./secrets.env" ]; then set -a; source ./secrets.env; set +a; fi

SYMS="${SYMS:-BTCUSDT ETHUSDT ADAUSDT SOLUSDT XRPUSDT}"
TFS="${TFS:-15m 1h 4h}"
LOOKBACK="${EVAL_LOOKBACK_DAYS:-365}"
TOPK="${TOP_K:-5}"
MINTR="${MIN_TRADES:-10}"

# Varmista riippuvuudet
source venv/bin/activate || true
pip install -q --upgrade pip
pip install -q ccxt pandas numpy scikit-learn joblib

echo "[auto] train models"
python scripts/train_all_models.py --symbols ${SYMS} --timeframes ${TFS} --lookback-days "${LOOKBACK}"

echo "[auto] evaluate + select (model-based)"
python scripts/model_evaluate_select.py --symbols ${SYMS} --timeframes ${TFS} --lookback-days "${LOOKBACK}" --top-k "${TOPK}" --min-trades "${MINTR}"

echo "[auto] restart live"
systemctl restart pro_botti || true

echo "[auto] done $(date -Iseconds)"
