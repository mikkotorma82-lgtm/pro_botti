#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trainer Loop (daemon)
- Käynnistää ai_train.py:n jatkuvasti
- Tallentaa tulokset data/train_history.json
- Lähettää Telegramiin raportin (jos asetettu)
"""
import os, time, subprocess, json, datetime, traceback
from pathlib import Path
BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"
LOGS = BASE / "logs"
HIST = DATA / "train_history.json"
LOGS.mkdir(exist_ok=True)
DATA.mkdir(exist_ok=True)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(msg: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    import urllib.request, urllib.parse
    try:
        data = urllib.parse.urlencode({"chat_id": TELEGRAM_CHAT_ID, "text": msg}).encode("utf-8")
        urllib.request.urlopen(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", data=data)
    except Exception:
        pass

while True:
    try:
        ts = datetime.datetime.utcnow().isoformat()
        log_file = LOGS / f"train_{ts}.log"
        with open(log_file, "w") as f:
            proc = subprocess.run(["python3", "ai_train.py"], cwd=str(BASE), stdout=f, stderr=f)
        # Jos treeni onnistui, lisätään historiatietoon aikaleima
        if not HIST.exists():
            json.dump([], open(HIST,"w"))
        data = json.load(open(HIST))
        data.append({"timestamp": ts, "status": "ok"})
        json.dump(data, open(HIST,"w"), indent=2)
        send_telegram(f"✅ Training finished at {ts}")
    except Exception as e:
        open(LOGS/"trainer_error.log","a").write(traceback.format_exc()+"\n")
        send_telegram(f"❌ Training error: {e}")
    time.sleep(60*60)  # tunnin välein
