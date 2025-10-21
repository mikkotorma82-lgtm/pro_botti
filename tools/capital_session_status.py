#!/usr/bin/env python3
from __future__ import annotations
import json, time
from pathlib import Path

def main():
    p = Path(__file__).resolve().parents[1] / "state" / "capital_session.json"
    if not p.exists():
        print("No session cache:", p)
        return
    obj = json.loads(p.read_text())
    ts = float(obj.get("login_time", 0) or 0)
    age = time.time() - ts if ts else -1
    print("Session cache:", p)
    print("login_time:", ts, "age_sec:", int(age))
    print("cst head:", (obj.get("cst") or "")[:8], "sec head:", (obj.get("sec") or "")[:8])

if __name__ == "__main__":
    main()
