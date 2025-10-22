#!/usr/bin/env python3
import subprocess, datetime
now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
try:
    subprocess.run(["git", "add", "-A"], check=True)
    subprocess.run(["git", "commit", "-m", f"Auto update {now}"], check=False)
    subprocess.run(["git", "push", "origin", "main"], check=True)
    print(f"[{now}] ✅ Auto Git push done")
except Exception as e:
    print(f"[{now}] ⚠️ Auto push failed:", e)
