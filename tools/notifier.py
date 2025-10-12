import os, time
try:
    from tools.tele import send as tgsend
except Exception:
    def tgsend(*a, **kw): return None

BOTNAME = os.getenv("TG_BOT_NAME", "📈 Bot")

def _send(text: str):
    tgsend(f"{BOTNAME} {text}")

# koulutus/backtest
def train_started(desc:str=""):
    _send(f"🛠️ Koulutus käynnistyy{(' ('+desc+')') if desc else ''}…")

def train_finished(pct:float, eq_end:float, eq_start:float, period:str):
    sign = "✅" if pct >= 0 else "❌"
    _send(f"{sign} Koulutus valmis ({period}) — tuotto {pct:.2f}% | ekv={eq_end:.2f}€ (alkaen {eq_start:.2f}€)")

# kaupat
def opened(sym:str, side:str, size:float, price:float):
    _send(f"🟢 Avattu {sym} {side} size={size:g} @ {price}")

def added(sym:str, side:str, add_size:float, price:float, total_size:float):
    _send(f"➕ Lisätty {sym} {side} +{add_size:g} @ {price} (yht. {total_size:g})")

def closed(sym:str, side:str, exit_size:float, price:float, pnl_abs:float|None, pnl_pct:float|None):
    emoji = "✅" if (pnl_abs or 0) >= 0 else "❌"
    if pnl_abs is None or pnl_pct is None:
        _send(f"{emoji} Suljettu {sym} {side} size={exit_size:g} @ {price} | P/L: ei laskettavissa (ei hintaa)")
    else:
        _send(f"{emoji} Suljettu {sym} {side} size={exit_size:g} @ {price} | P/L {pnl_abs:.2f}€ ({pnl_pct:.2f}%)")

# jaksotuotot
def period_pnl(kind:str, pnl_abs:float, pnl_pct:float, eq:float):
    emoji = "📅" if kind=="päivä" else ("🗓️" if kind=="viikko" else "📈")
    _send(f"{emoji} {kind.capitalize()}tuotto {pnl_abs:.2f}€ ({pnl_pct:.2f}%) | ekv={eq:.2f}€")
