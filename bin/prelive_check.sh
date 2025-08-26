#!/usr/bin/env bash
set -euo pipefail

say_ok(){   printf "[OK]   %s\n" "$*"; }
say_fail(){ printf "[FAIL] %s\n" "$*" >&2; }
die(){      say_fail "$*"; exit 1; }

# 0) Lataa ympäristö vain luentaan
set -a
[ -f /root/pro_botti/.env ]     && . /root/pro_botti/.env
[ -f /root/pro_botti/.env.bot ] && . /root/pro_botti/.env.bot
set +a

cd /root/pro_botti

# 1) Aktiivinen malli & kynnys (voit laajentaa models/active.json -logiikalla myöhemmin)
MODEL="models/current.joblib"
THR="${THR:-0.48}"
say_ok "Aktiivimalli: ${MODEL}, thr=${THR}"

# 2) risk.yaml: tarkista tai luo oletus
if [ ! -f config/risk.yaml ]; then
  install -d -m 0755 config
  cat > config/risk.yaml <<'YAML'
# Auto-created minimal risk config
atr:
  period: 14
risk_per_trade: 0.01
YAML
  say_ok "Loin oletus config/risk.yaml"
fi

# 3) YAML syntaksitesti
python - <<'PY' >/dev/null && say_ok "Riski YAML syntaksi OK" || { say_fail "Riski YAML virhe"; exit 1; }
import sys, yaml
with open("config/risk.yaml","r",encoding="utf-8") as f:
    yaml.safe_load(f)
PY

# 4) Paper trader savutesti
export HIST_CSV="${HIST_CSV:-data/EURUSD_15m.csv}"
python -m tools.paper_trade \
  --model "$MODEL" \
  --csv   "$HIST_CSV" \
  --thr   "$THR" \
  --equity0 "${EQUITY0:-10000}" \
  --out  "results/paper_smoke.json" >/dev/null

say_ok "Paper trader OK → results/paper_smoke.json"
