#!/usr/bin/env bash
set -euo pipefail

BASE="https://api-capital.backend-capital.com"
OUT="/root/pro_botti/data/capital_symbols_checked.csv"
mkdir -p "$(dirname "$OUT")"

source /root/pro_botti/secrets.env

# Login Capital.com APIin
read CST XSEC <<<"$(
  curl -sS -D- -X POST "$BASE/api/v1/session" \
    -H "X-CAP-API-KEY: $CAPITAL_API_KEY" -H "Content-Type: application/json" \
    --data "{\"identifier\":\"$CAPITAL_LOGIN\",\"password\":\"$CAPITAL_PASSWORD\"}" \
  | awk 'BEGIN{cst="";sec=""}
         tolower($1)=="cst:" {cst=$2}
         tolower($1)=="x-security-token:" {sec=$2}
         END{gsub(/\r/,"",cst); gsub(/\r/,"",sec); print cst" "sec}'
)"

# Symbolit joilla botti treidaa
SYMS=( EURUSD GBPUSD US500 US100 AAPL TSLA NVDA BTCUSD ETHUSD XRPUSD SOLUSD ADAUSD XAUUSD USDJPY GER40 )

echo "symbol,epic,name,minDealSize,marginFactor,leverage" >"$OUT"

for S in "${SYMS[@]}"; do
  echo ">>> Haetaan $S ..."
  J=$(curl -sS "$BASE/api/v1/markets/$S" \
        -H "X-CAP-API-KEY: $CAPITAL_API_KEY" \
        -H "CST: $CST" -H "X-SECURITY-TOKEN: $XSEC")

  epic=$(echo "$J" | jq -r '.instrument.epic // .epic // "-"')
  name=$(echo "$J" | jq -r '.instrument.name // .instrument.displayName // "-"')
  minsize=$(echo "$J" | jq -r '.dealingRules.minDealSize.value // "-"')
  margin=$(echo "$J" | jq -r '.instrument.marginFactor // .marginFactor // "-"')
  lev=$(echo "$J" | jq -r '.instrument.leverage // .leverage // "-"')

  echo "$S,$epic,\"$name\",$minsize,$margin,$lev" >>"$OUT"
done

echo "✅ Tulos tallennettu: $OUT"
