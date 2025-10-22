#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trader Engine – CapitalBot v10.1
✅ Lukee signaalit data/signals.json
✅ Käyttää CapitalClient (auto keep-alive)
✅ Logittaa kaikki tapahtumat logs/trader_engine.log
"""

import os, time, json, traceback
from pathlib import Path
from datetime import datetime
from capital_api import CapitalClient

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"
LOGS = BASE / "logs"
SIGNALS = DATA / "signals.json"
LOG_FILE = LOGS / "trader_engine.log"

os.makedirs(DATA, exist_ok=True)
os.makedirs(LOGS, exist_ok=True)

LIVE_TRADING = os.getenv("LIVE_TRADING", "0").strip() == "1"

def log(msg: str):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{ts} {msg}\n")

def load_signals():
    if not SIGNALS.exists():
        return []
    try:
        data = json.load(open(SIGNALS, "r", encoding="utf-8"))
        if isinstance(data, dict) and "queue" in data:
            return data["queue"]
        if isinstance(data, list):
            return data
    except Exception:
        log("[signals] JSON error")
    return []

def save_signals(queue):
    tmp = SIGNALS.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"queue": queue}, f, indent=2)
    tmp.replace(SIGNALS)

def process_signal(client: CapitalClient, sig: dict):
    epic = str(sig.get("epic") or sig.get("symbol") or "").upper()
    side = str(sig.get("side") or "").upper()
    size = float(sig.get("size") or 0)
    tp   = sig.get("tp")
    sl   = sig.get("sl")
    reason = sig.get("reason","")

    if not epic or side not in ("LONG","SHORT") or size <= 0:
        log(f"[skip] invalid signal {sig}")
        return True

    if not LIVE_TRADING:
        log(f"[DRYRUN] {epic} {side} size={size} tp={tp} sl={sl} reason='{reason}'")
        return True

    try:
        res = client.place_market_order(epic, side, size, stop=sl, limit=tp)
        if res.get("ok"):
            log(f"[order] OK {epic} {side} {size} tp={tp} sl={sl}")
            return True
        else:
            log(f"[order] FAIL {epic} {side} -> {res}")
            return False
    except Exception:
        log(f"[order] Exception:\n{traceback.format_exc()}")
        return False

def main():
    log(f"Trader Engine started (LIVE_TRADING={int(LIVE_TRADING)})")
    client = CapitalClient()
    if not client.login():
        log("[fatal] login failed")
        time.sleep(15)
        return

    while True:
        try:
            client.keep_alive()
            queue = load_signals()
            if queue:
                new_queue = []
                for sig in queue:
                    ok = process_signal(client, sig)
                    if not ok:
                        new_queue.append(sig)
                save_signals(new_queue)
            time.sleep(3)
        except KeyboardInterrupt:
            break
        except Exception:
            log("[loop] Exception:\n" + traceback.format_exc())
            time.sleep(5)

if __name__ == "__main__":
    main()
