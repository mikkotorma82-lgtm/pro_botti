#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hakee equity (oman pääoman) Capital.com API:sta ja päivittää data/equity_history.json
"""

import os, json, datetime
from pathlib import Path
from capital_api import CapitalClient

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"
DATA.mkdir(exist_ok=True)

def fetch_equity():
    client = CapitalClient()
    if not client.login():
        print("[equity] login failed")
        return
    info = client.get_account_info()
    try:
        acc = info["accounts"][0]
        balance = float(acc.get("balance", 0))
        equity = float(acc.get("equity", 0))
    except Exception:
        print("[equity] could not parse account info:", info)
        return
    eq_path = DATA / "equity_history.json"
    hist = {"entries": []}
    if eq_path.exists():
        try:
            hist = json.load(open(eq_path))
        except Exception:
            hist = {"entries": []}
    now = datetime.datetime.utcnow().isoformat()
    hist["entries"].append({"timestamp": now, "equity": equity, "balance": balance})
    json.dump(hist, open(eq_path, "w"), indent=2)
    print(f"[equity] {now} equity={equity:.2f} balance={balance:.2f}")

if __name__ == "__main__":
    fetch_equity()
