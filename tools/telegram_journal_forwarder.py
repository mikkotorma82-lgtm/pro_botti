# FORWARD_GUARD_INSERTED
import re

def _mute_line(line:str)->bool:
    return ("[DECISION]" in line) or ("[SIZE]" in line)

import os, re, time, sys

# Alkuperäiset regexit (pidetään, jos muualla käytössä)
R_DECISION = re.compile(r"\[DECISION\]\s+([A-Z0-9_]+)\s*->\s*(BUY|SELL|HOLD)", re.I)
R_SIZE     = re.compile(r"\[SIZE\]\s+(\S+)\s+min=([\d.]+)\s+step=([\d.]+)\s+used=([\d.]+)", re.I)

# Ympäristömuuttujat
SEND_HOLD = False
COOLDOWN_SECS = int(os.getenv("TG_DECISION_COOLDOWN", "600"))       # 10 min / symboli
MUTE_LIST     = {s.strip().upper() for s in os.getenv("TG_MUTE", "").split(",") if s.strip()}  # esim "AAPL,NVDA"
DROP_SIZE     = os.getenv("TG_NOTIFY_SIZE", "0") != "1"             # 1 = lähetä SIZE, muuten drop

_last_decision = {}
_last_sent_ts  = {}

def should_send_decision(sym:str, dec:str)->bool:
    now   = time.time()
    prev  = _last_decision.get(sym)
    lastt = _last_sent_ts.get(sym, 0.0)
    changed = (prev != dec)
    cool_ok = (now - lastt) > COOLDOWN_SECS
    if changed and cool_ok:
        _last_decision[sym] = dec
        _last_sent_ts[sym]  = now
        return True
    return False

def forward_line(line:str, send_func):
    if _mute_line(line):
        return
    # DROP SIZE?
    if DROP_SIZE and R_SIZE.search(line):
        return

    # DECISION suodatus
    m = R_DECISION.search(line)
    if m:
        sym = m.group(1).upper()
        dec = m.group(2).upper()

        if sym in MUTE_LIST:
            return
        if (not SEND_HOLD) and dec == "HOLD":
            return
        if should_send_decision(sym, dec):
            return None  # DECISION suppressed
        return

    # Muut rivit: lähetä vain jos start/ERROR
    if "käynnistyy:" in line or "[ERROR]" in line:
        return send_func(line[:4000])

def main(send_func):
    for line in sys.stdin:
        try:
            forward_line(line.rstrip("\n"), send_func)
        except Exception:
            pass
