#!/usr/bin/env bash
set -euo pipefail
ROOT=/root/pro_botti
set -a; [ -f "$ROOT/botti.env" ] && source "$ROOT/botti.env"; set +a

PY="${ROOT}/venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

exec "$PY" - <<'PY'
import os, json, sys
from capital_api import CapitalClient

root="/root/pro_botti"
# kerää symbolit
syms=[]
try:
    with open(f"{root}/config/active_symbols.txt","r",encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if not line or line.startswith("#"): continue
            syms.append(line)
except Exception as e:
    print("[ERR] active_symbols.txt:", e)
    sys.exit(0)

# lue overrides
try:
    with open(f"{root}/config/size_overrides.json","r",encoding="utf-8") as f:
        overrides=json.load(f)
except Exception:
    overrides={}

cli=CapitalClient()
print(f"ENV={cli.env} BASE={cli.base}")
print(f"{'SYMBOL':10s}  {'EPIC':15s}  {'API_min':>10s}  {'step':>10s}  {'override':>10s}  {'used(size)':>12s}  note")
for s in syms:
    epic=s
    api_min="N/A"; step="N/A"; used="N/A"; note=[]
    try:
        epic=cli.resolve_epic(s)
    except Exception as e:
        note.append("resolve_fail")

    ov = overrides.get(s)
    if ov is not None:
        used = str(ov)
        note.append("override")
    else:
        try:
            ms = cli.min_size_and_step(epic)
            api_min = f"{ms['min_size']}"
            step    = f"{ms['step']}"
            # käytä vähintään minimi ja pyöristä steppiin
            desired = ms['min_size']
            stp = ms['step'] if ms['step']>0 else 0.0
            if stp>0:
                import math
                desired = round(math.ceil((desired+1e-12)/stp)*stp, 8)
            used = f"{desired}"
        except Exception as e:
            note.append("api_unavailable")
            # fallback: SIZE_DEFAULT tai 1
            try:
                used = str(float(os.getenv("SIZE_DEFAULT","1")))
            except Exception:
                used = "1"

    print(f"{s:10s}  {epic:15s}  {api_min:>10s}  {step:>10s}  {str(ov):>10s}  {used:>12s}  {';'.join(note)}")
sys.exit(0)
PY
