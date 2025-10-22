#!/usr/bin/env bash
set -euo pipefail
cd /root/pro_botti
PY="/root/pro_botti/venv/bin/python"

# Lataa vain palvelun env
set -a
[ -f /pro_botti/botti.env ] && . /pro_botti/botti.env
set +a

# Peruscheckit
MODEL="$(jq -r .model models/active.json)"
THR="$(jq -r .thr   models/active.json)"
printf '[OK]   %s\n' "Aktiivimalli: $MODEL, thr=$THR"

# YAML syntaksi
$PY - <<'PYCHK'
import sys,yaml; yaml.safe_load(open('config/risk.yaml'))
PYCHK
printf '[OK]   %s\n' "Riski YAML syntaksi OK"

# Pieni paper-smoke omilla, kiinteillä arvoilla
CSV="${HIST_CSV:-data/EURUSD_15m.csv}"
$PY -m tools.paper_trade --model "$MODEL" --csv "$CSV" --thr "$THR" --equity0 10000 --out results/paper_smoke.json
printf '[OK]   %s\n' "Paper trader OK → results/paper_smoke.json"
