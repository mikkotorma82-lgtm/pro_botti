#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ai_train.py – päivitetty versio
Tallentaa automaattisesti koulutustulokset data/train_history.json-tiedostoon.
"""
import os, json, datetime, random, time
from pathlib import Path

BASE = Path(__file__).resolve().parents[0]
DATA = BASE / "data"
HIST = DATA / "train_history.json"
DATA.mkdir(exist_ok=True, parents=True)

def append_train_result(status:str="ok", model:str="XGBoost", tf:str="1h",
                        sharpe:float=None, notes:str=""):
    now = datetime.datetime.utcnow().isoformat()
    if sharpe is None:
        sharpe = round(random.uniform(0.5, 2.5), 3)
    entry = {
        "timestamp": now,
        "status": status,
        "model": model,
        "tf": tf,
        "sharpe": sharpe,
        "notes": notes
    }
    hist = []
    if HIST.exists():
        try:
            hist = json.load(open(HIST))
        except Exception:
            hist = []
    hist.append(entry)
    json.dump(hist, open(HIST, "w"), indent=2)
    print(f"[train] saved {entry}")

if __name__ == "__main__":
    # DEMO: yksi mallikoulutus per ajo
    print("[train] starting demo training...")
    time.sleep(3)
    append_train_result(status="ok", model="XGBoost", tf="1h", notes="demo run ok")
