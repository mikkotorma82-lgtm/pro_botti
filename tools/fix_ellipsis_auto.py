#!/usr/bin/env python3
import os, re
from pathlib import Path

root = Path("/root/pro_botti")
pattern_self = re.compile(rb'(\s*self\.capital\s*=\s*)\.\.\.')
pattern_return = re.compile(rb'(\s*return\s*)\.\.\.')

replaced = 0
for path in root.rglob("*.py"):
    if "venv" in str(path) or "site-packages" in str(path):
        continue
    try:
        data = open(path, "rb").read()
    except Exception:
        continue
    if b"..." not in data:
        continue
    fixed = data
    if pattern_self.search(data):
        fixed = pattern_self.sub(rb'\1CapitalClient()', fixed)
        replaced += 1
        print(f"[FIXED] self.capital -> CapitalClient() in {path}")
    if pattern_return.search(data):
        fixed = pattern_return.sub(rb'\1self.capital', fixed)
        replaced += 1
        print(f"[FIXED] return self.capital -> return self.capital in {path}")
    if fixed != data:
        if b"CapitalClient" not in fixed:
            fixed = b'from capital_api import CapitalClient\n' + fixed
        with open(path, "wb") as f:
            f.write(fixed)

print(f"\n✅ Done. {replaced} replacements made (venv excluded).")
