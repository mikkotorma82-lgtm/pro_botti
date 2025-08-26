#!/usr/bin/env bash
set -euo pipefail
cd /root/pro_botti
[ -d venv ] && . venv/bin/activate
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_MAX_THREADS=1 MALLOC_ARENA_MAX=2
mkdir -p logs
while true; do
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "[$ts] running live_signals..." | tee -a logs/loop.log
  python3 -m tools.live_signals --symbols US500 EURUSD GBPUSD --tf 1h --thr_buy 0.10 --thr_sell 0.10 \
    > "logs/live_1h_${ts}.json" 2>> logs/loop.err || true
  sleep 300  # 5 min
done
