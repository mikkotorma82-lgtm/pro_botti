#!/usr/bin/env bash
set -euo pipefail

BASE="https://api-capital.backend-capital.com"
SYMLIST="/root/pro_botti/data/selected_symbols.csv"
OUT="/root/pro_botti/data/capital_rules_checked.csv"

if [ ! -f /root/pro_botti/secrets.env ]; then
  echo "Missing /root/pro_botti/secrets.env" >&2
  exit 1
fi
source /root/pro_botti/secrets.env

login() {
  # Hae CST ja X-SECURITY-TOKEN
  read CST XSEC <<<"$(
    curl -sS -D- -X POST "$BASE/api/v1/session" \
      -H "X-CAP-API-KEY: $CAPITAL_API_KEY" -H "Content-Type: application/json" \
      --data "{\"identifier\":\"$CAPITAL_LOGIN\",\"password\":\"$CAPITAL_PASSWORD\"}" \
    | awk 'BEGIN{cst="";sec=""}
           tolower($1)=="cst:" {cst=$2}
           tolower($1)=="x-security-token:" {sec=$2}
           END{gsub(/\r/,"",cst); gsub(/\r/,"",sec); print cst" "sec}'
  )"
  echo "$CST" "$XSEC"
}

fetch_market_json() {
  local epic="$1" cst="$2" xsec="$3"
  curl -sS "$BASE/api/v1/markets/$epic" \
    -H "X-CAP-API-KEY: $CAPITAL_API_KEY" \
    -H "CST: $cst" -H "X-SECURITY-TOKEN: $xsec"
}

resolve_epic() {
  # Yritä /markets/{symbol}; jos ei löydy, haku /markets?search=symbol
  local symbol="$1" cst="$2" xsec="$3"
  local j
  j=$(curl -sS "$BASE/api/v1/markets/$symbol" \
        -H "X-CAP-API-KEY: $CAPITAL_API_KEY" \
        -H "CST: $cst" -H "X-SECURITY-TOKEN: $xsec")
  # jos vastauksessa on .instrument.epic, käytä sitä
  echo "$j" | jq -er '.instrument.epic // .epic' 2>/dev/null && return 0

  # fallback: haku
  j=$(curl -sS "$BASE/api/v1/markets?search=$symbol" \
        -H "X-CAP-API-KEY: $CAPITAL_API_KEY" \
        -H "CST: $cst" -H "X-SECURITY-TOKEN: $xsec")
  # Poimi paras osuma: täsmälleen sama marketId jos löytyy, muuten ensimmäinen instrumentti
  echo "$j" | jq -er --arg s "$symbol" '
      ( .markets[]? | select(.instrument.marketId==$s) | .instrument.epic ) //
      ( .markets[0]?.instrument.epic )
  ' 2>/dev/null
}

readarray -t HEADER < <(head -n1 "$SYMLIST")
if [ "${HEADER[0]}" != "symbol,epic" ] && [ "${HEADER[0]}" != "symbol,epic,name" ]; then
  echo "selected_symbols.csv should have header: symbol,epic" >&2
fi

CST_XSEC=($(login))
CST="${CST_XSEC[0]}"
XSEC="${CST_XSEC[1]}"

echo "symbol,epic,name,dealingStatus,minDealSize.value,minDealSize.unit,marginFactor,leverage" >"$OUT"

# Lue symbolit (ohita otsikko)
tail -n +2 "$SYMLIST" | while IFS=, read -r symbol epic_rest; do
  # Poista ympäriltä mahdolliset lainausmerkit/tyhjät
  symbol="${symbol%\"}"; symbol="${symbol#\"}"
  symbol="${symbol//[$'\r\t ']/}"

  # Jos epic tyhjä, yritä resolvointi
  epic="$(echo "$epic_rest" | cut -d, -f1)"
  epic="${epic%\"}"; epic="${epic#\"}"
  epic="${epic//[$'\r\t ']/}"

  if [ -z "$epic" ] || [ "$epic" = "nan" ]; then
    epic="$(resolve_epic "$symbol" "$CST" "$XSEC" || true)"
  fi
  if [ -z "$epic" ]; then
    echo "WARN: $symbol -> EPIC not found" >&2
    continue
  fi

  j="$(fetch_market_json "$epic" "$CST" "$XSEC" || true)"
  if [ -z "$j" ] || echo "$j" | jq -e '.errorCode? | length>0' >/dev/null 2>&1; then
    echo "WARN: failed to fetch market for $symbol ($epic)" >&2
    continue
  fi

  name=$(echo "$j" | jq -r '.instrument.name // .instrument.displayName // "-"')
  dealing=$(echo "$j" | jq -r '.dealingRules?.status // .snapshot?.status // "-"')
  minv=$(echo "$j" | jq -r '.dealingRules?.minDealSize?.value // .dealingRules?.minDealSize?.minimum // "-"')
  minu=$(echo "$j" | jq -r '.dealingRules?.minDealSize?.unit  // "-"')
  margin=$(echo "$j" | jq -r '.instrument?.marginFactor // .marginFactor // "-"')
  lev=$(echo "$j" | jq -r '.instrument?.leverage     // .leverage     // "-"')

  printf '%s,%s,"%s",%s,%s,%s,%s,%s\n' \
    "$symbol" "$epic" "$name" "$dealing" "$minv" "$minu" "$margin" "$lev" >>"$OUT"
done

echo "OK -> $OUT"
