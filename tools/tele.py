import os, requests, pathlib

# === GLOBAL DECISION THROTTLE START ===
# Pudottaa toistuvat DECISION-viestit (vain muuttuessa + 10min/symboli)
import re as _re, time as _time
_DEC_LAST = {}
_DEC_TS   = {}
_DEC_COOLDOWN = 600  # 10min

def _wrap_send(_orig):
    def _inner(msg, *a, **kw):
        m = _re.search(r'DECISION\s+([A-Z0-9_]+)\s*->\s*([A-Z]+)', str(msg))
        if m:
            sym, dec = m.group(1), m.group(2)
            now = _time.time()
            changed = (_DEC_LAST.get(sym) != dec)
            if changed and (now - _DEC_TS.get(sym, 0)) > _DEC_COOLDOWN:
                _DEC_LAST[sym] = dec
                _DEC_TS[sym] = now
                return _orig(msg, *a, **kw)
            return None  # hiljennä spämmi
        return _orig(msg, *a, **kw)
    return _inner

try:
    # wrapataan send vain kerran
    if 'send' in globals() and not globals().get('_SEND_WRAPPED'):
        send = _wrap_send(send)
        _SEND_WRAPPED = True
except Exception as e:
    # ei kaadeta lähetyksiä jos jokin menee pieleen
    import logging as _logging
    _logging.getLogger(__name__).warning("tele throttle init failed: %s", e)
# === GLOBAL DECISION THROTTLE END ===

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT  = os.environ.get("TELEGRAM_CHAT_ID", "")

def enabled():
    return os.environ.get("TELEGRAM_ENABLE","1") == "1" and TOKEN and CHAT

def send(text: str):
    # DROP all DECISION messages universally
    import re as _re, os as _os
    _t = locals().get('text') if 'text' in locals() else (args[0] if 'args' in locals() and args else '')
    if _t and (('[DECISION]' in _t) or (' DECISION ' in _t) or _t.startswith('📊 DECISION') or _re.search(r'\bDECISION\b', _t)):
        return None
    if not enabled(): return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                          data={"chat_id": CHAT, "text": text, "parse_mode":"Markdown"})
        return r.ok
    except Exception:
        return False

def send_photo(path: str, caption: str=""):
    if not enabled(): return False
    try:
        p = pathlib.Path(path)
        if not p.exists(): return False
        with p.open("rb") as f:
            r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendPhoto",
                              data={"chat_id": CHAT, "caption": caption, "parse_mode":"Markdown"},
                              files={"photo": f})
        return r.ok
    except Exception:
        return False


# === GLOBAL DECISION THROTTLE v2 ===
# Suodata DECISION-viestit: läpi vain kun päätös vaihtuu + 10min/symboli
import re as _re, time as _time
try:
    _DEC_LAST; _DEC_TS; _DEC_COOLDOWN
except NameError:
    _DEC_LAST, _DEC_TS, _DEC_COOLDOWN = {}, {}, 600

def _dec_wrap(_orig):
    def _inner(text, *a, **kw):
        m=_re.search(r'DECISION\s+([A-Z0-9_]+)\s*->\s*(HOLD|BUY|SELL)', str(text))
        if m:
            sym, dec = m.group(1), m.group(2)
            now=_time.time()
            if _DEC_LAST.get(sym)!=dec and (now-_DEC_TS.get(sym,0))>_DEC_COOLDOWN:
                _DEC_LAST[sym]=dec; _DEC_TS[sym]=now
                return _orig(text,*a,**kw)
            return None  # hiljennä
        return _orig(text,*a,**kw)
    return _inner

try:
    send = _dec_wrap(send)  # wrapataan vasta kun send on varmasti määritelty
except Exception:
    pass
# === END GLOBAL DECISION THROTTLE v2 ===

