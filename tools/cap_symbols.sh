#!/usr/bin/env bash
set -euo pipefail

BASE="https://api-capital.backend-capital.com"
OUT="/root/pro_botti/data/capital_symbols.csv"
mkdir -p "$(dirname "$OUT")"
source /root/pro_botti/secrets.env

# --- Login (CST + XSEC) ---
read CST XSEC <<<"$(
  curl -sS -D- -X POST "$BASE/api/v1/session" \
    -H "X-CAP-API-KEY: $CAPITAL_API_KEY" -H "Content-Type: application/json" \
    --data "{\"identifier\":\"$CAPITAL_LOGIN\",\"password\":\"$CAPITAL_PASSWORD\"}" \
  | awk 'BEGIN{cst="";sec=""}
         tolower($1)=="cst:" {cst=$2}
         tolower($1)=="x-security-token:" {sec=$2}
         END{gsub(/\r/,"",cst); gsub(/\r/,"",sec); print cst" "sec}'
)"

hdr_common=( -H "X-CAP-API-KEY: $CAPITAL_API_KEY" -H "CST: $CST" -H "X-SECURITY-TOKEN: $XSEC" )

# CSV header
echo "symbol,epic,type,expiry,marginFactor,minDealSize" > "$OUT"

# Hae juurisolmu
ROOT_JSON="$(curl -sS "$BASE/api/v1/marketnavigation" "${hdr_common[@]}")"

# Jono alinodeille
mapfile -t queue < <( echo "$ROOT_JSON" | jq -r '.nodes[]?.id' )

# Dumppaa juuren markets (jos on)
echo "$ROOT_JSON" \
| jq -rc '.markets[]? | {
    symbol: (.instrument.marketId // .instrument.name // .instrument.displayName // .epic // "-"),
    epic:   (.epic // .instrument.epic // "-"),
    type:   (.instrument.type // .instrument.assetClass // "-"),
    expiry: (.instrument.expiry // "-"),
    margin: (.instrument.marginFactor // .dealingRules.marginFactor // .marginFactor // null),
    minsz:  (.dealingRules.minDealSize.value // .dealingRules.minDealSize // null)
  } | [ .symbol, .epic, .type, .expiry, (.margin//""), (.minsz//"") ] | @csv' \
>> "$OUT"

# BFS: käy läpi koko puu
while ((${#queue[@]})); do
  id="${queue[0]}"
  queue=("${queue[@]:1}")

  json="$(curl -sS "$BASE/api/v1/marketnavigation/$id" "${hdr_common[@]}")"

  # Lisää lapsinodet
  while IFS= read -r nid; do
    [[ -n "$nid" ]] && queue+=("$nid")
  done < <(echo "$json" | jq -r '.nodes[]?.id')

  # Tallenna node:n markets
  echo "$json" \
  | jq -rc '.markets[]? | {
      symbol: (.instrument.marketId // .instrument.name // .instrument.displayName // .epic // "-"),
      epic:   (.epic // .instrument.epic // "-"),
      type:   (.instrument.type // .instrument.assetClass // "-"),
      expiry: (.instrument.expiry // "-"),
      margin: (.instrument.marginFactor // .dealingRules.marginFactor // .marginFactor // null),
      minsz:  (.dealingRules.minDealSize.value // .dealingRules.minDealSize // null)
    } | [ .symbol, .epic, .type, .expiry, (.margin//""), (.minsz//"") ] | @csv' \
  >> "$OUT"
done

# Unikoi + näytä esimerkkirivejä
TMP="$(mktemp)"
{ head -n1 "$OUT"; tail -n +2 "$OUT" | sort -u; } > "$TMP"
mv "$TMP" "$OUT"

echo ">> Täysi CSV valmis: $OUT (rivit: $(wc -l < "$OUT"))"
echo ">> Esimerkkejä (haetaan muutama tuttu):"
grep -E '(^|,)(XRPUSD|BTCUSD|ETHUSD|EURUSD|US500|GER40)(,|$)' "$OUT" | head -n 20 || true
