#!/usr/bin/env python3
import os, re

root = "/root/pro_botti"
pattern = re.compile(rb'(\s*)(self\.\w+)\s*=\s*\.\.\.')
replacement = rb'\1from capital_api import CapitalClient\n\1\2 = CapitalClient()'

for dirpath, _, files in os.walk(root):
    for f in files:
        if f.endswith(".py"):  # korjattu: käytetään str, ei bytes
            path = os.path.join(dirpath, f)
            try:
                with open(path, "rb") as infile:
                    data = infile.read()
            except Exception as e:
                print(f"[SKIP] {path}: {e}")
                continue
            if b"..." in data:
                fixed = re.sub(pattern, replacement, data)
                if fixed != data:
                    with open(path, "wb") as outfile:
                        outfile.write(fixed)
                    print(f"[FIXED] {path}")
