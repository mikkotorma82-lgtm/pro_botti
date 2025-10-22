#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Risk Engine Loop (daemon)
- Käynnistää core/portfolio_risk.py säännöllisesti
- Päivittää data/risk_state.json ja data/risk_history.json
"""
import os, time, subprocess, json, datetime, traceback
from pathlib import Path
BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"
LOGS = BASE / "logs"
STATE = DATA / "risk_state.json"
HIST  = DATA / "risk_history.json"
LOGS.mkdir(exist_ok=True)
DATA.mkdir(exist_ok=True)

while True:
    try:
        ts = datetime.datetime.utcnow().isoformat()
        log_file = LOGS / f"risk_{ts}.log"
        subprocess.run(["python3", "core/portfolio_risk.py"], cwd=str(BASE),
                       stdout=open(log_file,"w"), stderr=open(log_file,"a"))
        # jos risk_state päivitetty, lisää historiaan
        if STATE.exists():
            state = json.load(open(STATE))
            hist = json.load(open(HIST)) if HIST.exists() else {"entries":[]}
            state["timestamp"] = ts
            hist["entries"].append(state)
            json.dump(hist, open(HIST,"w"), indent=2)
    except Exception:
        open(LOGS/"risk_engine_error.log","a").write(traceback.format_exc()+"\n")
    time.sleep(60*15)  # 15 minuutin välein
