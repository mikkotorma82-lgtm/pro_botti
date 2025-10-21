import os, json, time
from pathlib import Path
import pandas as pd

ROOT = Path(os.environ.get("ROOT","/root/pro_botti"))
RESULTS = ROOT/"results"; RESULTS.mkdir(parents=True, exist_ok=True)
STATE = ROOT/"state"; STATE.mkdir(parents=True, exist_ok=True)

LEDGER_CSV = RESULTS/"trades.csv"
POS_JSON   = STATE/"positions.json"

def _now_ms(): return int(time.time()*1000)

def append_trade(symbol, tf, side, price, amount, mode, p=None, why=None, order_id=None, fee=None):
    row = {
        "ts": _now_ms(),
        "symbol": symbol, "tf": tf, "side": side,
        "price": float(price), "amount": float(amount),
        "notional": float(price)*float(amount),
        "mode": mode, "p": (None if p is None else float(p)),
        "why": (why or ""), "order_id": (order_id or ""), "fee": (fee or 0.0)
    }
    df = pd.DataFrame([row])
    hdr = not LEDGER_CSV.exists()
    df.to_csv(LEDGER_CSV, index=False, mode="a", header=hdr)
    return row

def load_positions():
    if POS_JSON.exists():
        return json.loads(POS_JSON.read_text())
    return {}

def save_positions(pos):
    POS_JSON.write_text(json.dumps(pos, indent=2, sort_keys=True))

def update_position_on_fill(symbol, side, qty, price, allow_shorts=False):
    """
    Pitää vain *pitkät* oletuksena (allow_shorts=False). 
    BUY kasvattaa positiota, SELL pienentää. Negatiiviseen ei mennä, loput ohitetaan.
    """
    pos = load_positions()
    p = pos.get(symbol, {"qty":0.0,"avg":0.0,"realized":0.0})

    qty = float(qty); price = float(price)
    if side == "BUY":
        new_qty  = p["qty"] + qty
        if new_qty <= 0:  # outo kulma
            p["qty"], p["avg"] = 0.0, 0.0
        else:
            p["avg"] = (p["avg"]*p["qty"] + price*qty)/new_qty
            p["qty"] = new_qty
    elif side == "SELL":
        sell_qty = min(p["qty"] if not allow_shorts else qty, qty)
        # realisoitu PnL siitä osasta jonka suljemme
        p["realized"] += (price - p["avg"])*sell_qty
        p["qty"] -= sell_qty
        if p["qty"] <= 1e-12:
            p["qty"], p["avg"] = 0.0, 0.0
        # jos shortsit ei sallittuja, ylimenevä osa ignoroidaan

    pos[symbol] = p
    save_positions(pos)
    return p
