#!/usr/bin/env bash
set -euo pipefail
ROOT=/root/pro_botti
set -a; [ -f "$ROOT/botti.env" ] && source "$ROOT/botti.env"; set +a
PY="$ROOT/venv/bin/python"
SYMFILE="$ROOT/config/active_symbols.txt"

$PY - <<'PY'
import os, json
from capital_api import CapitalClient
root="/root/pro_botti"
syms=[]
with open(f"{root}/config/active_symbols.txt") as f:
    for line in f:
        line=line.strip()
        if not line or line.startswith("#"): continue
        syms.append(line)
try:
    with open(f"{root}/config/size_overrides.json","r",encoding="utf-8") as f:
        ov=json.load(f)
except Exception:
    ov={}
cli=CapitalClient()
print("ENV:", cli.env, "BASE:", cli.base)
for s in syms:
    epic=cli.resolve_epic(s)
    ms=cli.min_size_and_step(epic)
    o=ov.get(s)
    print(f"{s:10s} -> epic={epic:>12s}  API_min={ms['min_size']} step={ms['step']} override={o}")
PY
