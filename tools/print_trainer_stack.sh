#!/usr/bin/env bash
set -euo pipefail
OUT="/root/pro_botti/_dump/trainer_stack_$(date +%Y%m%d_%H%M%S).txt"
mkdir -p "$(dirname "$OUT")"

echo "### UNIT: pro-botti-trainer.service"            | tee "$OUT"
(systemctl cat pro-botti-trainer.service || true)     | tee -a "$OUT"
echo                                                 | tee -a "$OUT"

echo "### STATUS: pro-botti-trainer (last 150 lines)" | tee -a "$OUT"
(journalctl -u pro-botti-trainer.service -n 150 --no-pager || true) | tee -a "$OUT"
echo                                                 | tee -a "$OUT"

# Mitkä trainer-servicet ylipäätään asennettu
echo "### ENABLED/LINKED TRAIN SERVICES" | tee -a "$OUT"
(systemctl list-unit-files | egrep -i 'botti|trainer|train|ai' || true) | tee -a "$OUT"
echo                                   | tee -a "$OUT"

# Koodit, joita yleensä trainer käyttää
FILES=(
  tools/trainer_daemon.py
  tools/train_loop.py
  tools/train_core.py
  tools/trainer_v2.py
  tools/train_driver.py
  tools/train_models.py
  tools/ai_gate.py
  tools/model_utils.py
)

for f in "${FILES[@]}"; do
  p="/root/pro_botti/$f"
  if [[ -f "$p" ]]; then
    echo "===== BEGIN $f ====="         | tee -a "$OUT"
    sed -n '1,99999p' "$p"             | tee -a "$OUT"
    echo "===== END $f ====="           | tee -a "$OUT"
    echo                                | tee -a "$OUT"
  fi
done

# (valinnainen) käytössä olevat symbolit & instrumenttikartta
if [[ -f /root/pro_botti/config/active_symbols.txt ]]; then
  echo "===== BEGIN config/active_symbols.txt ====="  | tee -a "$OUT"
  cat /root/pro_botti/config/active_symbols.txt      | tee -a "$OUT"
  echo "===== END config/active_symbols.txt ====="    | tee -a "$OUT"
  echo                                                | tee -a "$OUT"
fi

if [[ -f /root/pro_botti/data/instrument_map.json ]]; then
  echo "===== BEGIN data/instrument_map.json (head) =====" | tee -a "$OUT"
  head -n 200 /root/pro_botti/data/instrument_map.json     | tee -a "$OUT"
  echo "===== END data/instrument_map.json (head) ====="   | tee -a "$OUT"
  echo                                                     | tee -a "$OUT"
fi

echo ">>> Snapshot tallennettu: $OUT" | tee -a "$OUT"
