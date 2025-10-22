#!/usr/bin/env bash
set -euo pipefail

ROOT=${ROOT:-/root/pro_botti}
cd "$ROOT" 2>/dev/null || { echo "Ei ROOT-kansiota: $ROOT"; exit 1; }

sep() {
  local path="$1"
  local sha=""
  if command -v sha256sum >/dev/null 2>&1 && [ -f "$path" ]; then
    sha=$(sha256sum "$path" | awk '{print $1}')
  fi
  local mtime=""
  if [ -e "$path" ]; then
    mtime=$(date -r "$path" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || true)
  fi
  echo
  echo "################################################################################"
  echo "# FILE: $path"
  [ -n "$mtime" ] && echo "# MTIME: $mtime"
  [ -n "$sha" ]   && echo "# SHA256: $sha"
  echo "################################################################################"
}

mask_env() {
  # Maskeeraa avaimet/salasanat/jwt:t, mutta säilyttää alku- ja loppupään lyhyesti
  sed -E \
    -e 's/(API_KEY|OPENAI_API_KEY|CAPITAL_API_KEY|TELEGRAM_BOT_TOKEN|BOT_TOKEN|PASSWORD|PASS|SECRET|ACCESS_TOKEN|REFRESH_TOKEN|BEARER|JWT|SESSION_SECRET|CAPITAL_PASSWORD)=.*/\1=****MASKED****/I' \
    -e 's/(CAPITAL_LOGIN|CAPITAL_IDENTIFIER|TELEGRAM_CHAT_ID)=([^[:space:]]+)/\1=\2/gI'
}

print_file() {
  local f="$1"
  if [ ! -e "$f" ]; then return; fi
  sep "$f"
  case "$(basename "$f")" in
    .env|*.env|botti.env|*.secrets|secrets.*)
      nl -ba "$f" | mask_env
      ;;
    *)
      nl -ba "$f"
      ;;
  esac
}

echo "== YLEISTIEDOT =="
echo "PWD: $(pwd)"
echo "Host: $(hostname)"
echo "Python: $(command -v python3 || true) ($(python3 -V 2>/dev/null || echo -n))"
echo

echo "== GIT-TILA (jos käytössä) =="
if [ -d .git ]; then
  git --no-pager status -sb || true
  git --no-pager log --oneline -n 3 || true
  echo
fi

echo "== SERVICE-TILA =="
if systemctl is-enabled pro-botti.service >/dev/null 2>&1; then
  systemctl status pro-botti.service --no-pager -l || true
fi
echo

# Lista selkeistä ykköstiedostoista
FILES=(
  "capital_api.py"
  "launch.sh"
  "requirements.txt"
  "botti.env"
  "config/active_symbols.txt"
  "config/sizes.json"
  "/etc/systemd/system/pro-botti.service"
)

# Kerää dynaamisesti tools/ ja config/ sisällöt
shopt -s nullglob
for f in tools/*.py tools/*.sh; do FILES+=("$f"); done
for f in config/*; do FILES+=("$f"); done
shopt -u nullglob

# Tulosta tiedostot
for f in "${FILES[@]}"; do
  print_file "$f"
done

echo
echo "== VIIMEISET LOKIT =="
journalctl -u pro-botti.service -n 200 --no-pager 2>/dev/null | sed -E 's/(Bearer [A-Za-z0-9\._-]+)/Bearer ****MASKED****/g' || true

echo
echo "== HAKU VIRHE- JA KAUPPA-RIVEISTÄ (nopea) =="
journalctl -u pro-botti.service -n 400 --no-pager 2>/dev/null \
  | egrep -i '\[TRADE\]|\[SIZE\]|\[CAPITAL\]|\[CONFIRM\]|\[ERROR\]|\bHTTP\b' || true

echo
echo "== VALMIS =="
