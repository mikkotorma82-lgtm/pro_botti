#!/usr/bin/env python3
import os, re
from pathlib import Path

root = Path("/root/pro_botti")
pattern_assign = re.compile(rb'(\s*self\.capital\s*=\s*)\.\.\.')
pattern_return = re.compile(rb'(\s*return\s*)\.\.\.')

def ensure_import(data: bytes) -> bytes:
    if b"from capital_api import CapitalClient" not in data:
        return b'from capital_api import CapitalClient\n' + data
    return data

count = 0
for path in root.rglob("*.py"):
    if "venv" in str(path) or "site-packages" in str(path):
        continue
    try:
        raw = open(path, "rb").read()
    except Exception:
        continue
    if b"..." not in raw:
        continue
    new = raw
    if pattern_assign.search(raw):
        new = pattern_assign.sub(rb'\1CapitalClient()', new)
        count += 1
        print(f"[FIXED] self.capital = CapitalClient() in {path}")
    if pattern_return.search(raw):
        new = pattern_return.sub(rb'\1self.capital', new)
        count += 1
        print(f"[FIXED] return self.capital in {path}")
    if new != raw:
        new = ensure_import(new)
        with open(path, "wb") as f:
            f.write(new)

print(f"\n✅ Ellipsis placeholder fix completed. {count} replacements made.")
