#!/usr/bin/env bash
set -euo pipefail

say_ok(){ printf "[OK]   %s\n" "$*"; }
say_fail(){ printf "[FAIL] %s\n" "$*" >&2; }
die(){ say_fail "$*"; exit 1; }

# Lataa ympäristömuuttujat vain luentaan (ei ylikirjoituksia)
set -a
[ -f /root/pro_botti/.env ] && . /root/pro_botti/.env
[ -f /root/pro_botti/.env.bot ] && . /root/pro_botti/.env.bot
set +a

cd /root/pro_botti

# 1) Aktiivinen malli & kynnys
if [ -f models/active.json ]; then
  MODEL=$(jq -r '.model' models/active.json)
  THR=$(jq -r '.thr'   models/active.json)
else
  MODEL="models/current.joblib"
  THR="0.48"
fi
say_ok "Aktiivimalli: $MODEL, thr=$THR"

# 2) Riskikonffin syntaksi
python - <<'PY' >/dev/null
import yaml
yaml.safe_load(open("config.risk.yaml"))
print("OK")
PY
say_ok "Riski YAML syntaksi OK"

# 3) Paper-traderin savutesti (vaatii CSV:n)
CSV="${HIST_CSV:-data/EURUSD_15m.csv}"
python -m tools.paper_trade \
  --model "$MODEL" \
  --csv   "$CSV" \
  --thr   "$THR" \
  --equity0 10000 \
  --out  results/paper_smoke.json \
  >/dev/null
say_ok "Paper trader OK → results/paper_smoke.json"
