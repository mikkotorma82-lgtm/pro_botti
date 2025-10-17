#!/usr/bin/env bash
set -euo pipefail
AGE_HOURS="${MODEL_MIN_AGE_HOURS:-12}"
pro="/root/pro_botti/state/models_pro.json"
meta="/root/pro_botti/state/models_meta.json"
# Force-ohitus: ympäristö tai lippu-tiedosto
if [[ "${FORCE_TRAIN:-0}" == "1" ]] || [[ -f "/root/pro_botti/state/force-train" ]]; then
  echo "[BUNDLE-GUARD] FORCE_TRAIN -> allow bundle"
  exit 0
fi
is_stale() {
  local f="$1"
  [[ ! -f "$f" ]] && return 0
  local mtime epoch_now age_sec
  mtime="$(stat -c %Y "$f")"
  epoch_now="$(date +%s)"
  age_sec="$((epoch_now - mtime))"
  [[ "$age_sec" -ge "$((AGE_HOURS*3600))" ]]
}
if is_stale "$pro" || is_stale "$meta"; then
  echo "[BUNDLE-GUARD] models are stale -> run training"
  exit 0
else
  echo "[BUNDLE-GUARD] models fresh (< ${AGE_HOURS}h) -> skip training"
  exit 100
fi
