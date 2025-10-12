#!/usr/bin/env bash
set -euo pipefail
cd /root/pro_botti/data/history

declare -A MAP=(
  [BTCUSD_15m.parquet]=BTCUSDT_15m.parquet
  [BTCUSD_1h.parquet]=BTCUSDT_1h.parquet
  [ETHUSD_15m.parquet]=ETHUSDT_15m.parquet
  [ETHUSD_1h.parquet]=ETHUSDT_1h.parquet
)

for LINK in "${!MAP[@]}"; do
  TARGET="${MAP[$LINK]}"
  if [[ -f "$TARGET" ]]; then
    if [[ ! -L "$LINK" || "$(readlink "$LINK" || true)" != "$TARGET" ]]; then
      ln -sfn "$TARGET" "$LINK"
      echo "[ensure_usd_links] set $LINK -> $TARGET"
    fi
  else
    echo "[ensure_usd_links] WARNING: target missing: $TARGET" >&2
  fi
done
