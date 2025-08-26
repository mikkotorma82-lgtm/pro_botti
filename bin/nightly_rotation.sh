#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source venv/bin/activate
set -a; . botti.env; set +a

# Backfill kaikille TF:ille
python3 -m tools.backfill --tf 15m
python3 -m tools.backfill --tf 1h
python3 -m tools.backfill --tf 4h

# WFA
python3 -m tools.wfa_batch

# Päivitä aktiiviset ROI-filtterillä
python3 -m tools.rotation
