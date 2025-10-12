# --- Simple runtime entrypoints for systemd ---

import os, time, sys
from tools.live_daemon import get_bid_ask

def live_loop():
    """
    Yksinkertainen live-loop: hakee [PRICE]-rivit TRADE_SYMBOLS-listalle.
    Kunnioittaa DRY_RUN=1 (ei lähetä tilauksia; me emme lähetä tässä muutenkaan).
    """
    symbols = [s.strip().upper() for s in os.getenv("TRADE_SYMBOLS"," ").split(",") if s.strip()]
    if not symbols:
        symbols = ["US500","US100","DE40","UK100","JP225"]

    print(f"[AIGATE] start symbols={symbols}")
    while True:
        for s in symbols:
            try:
                ba = get_bid_ask(s)
                if isinstance(ba, tuple) and len(ba) == 2 and all(isinstance(x,(int,float)) for x in ba if x is not None):
                    bid, ask = ba
                    if bid is not None and ask is not None:
                        print(f"[PRICE] {s} bid={bid} ask={ask}", flush=True)
                    else:
                        print(f"[PRICE] {s} (no snapshot)", flush=True)
                else:
                    print(f"[PRICE] {s} (unavailable)", flush=True)
            except Exception as e:
                print(f"[ERR] PRICE {s} {e}", flush=True)
        time.sleep(float(os.getenv("TICK_SLEEP", "5")))

def main():
    """
    Oletus entry: aja live_loop.
    Voit vaihtaa systemd:ssä ENTRY_FN=live_loop/main.
    """
    try:
        live_loop()
    except KeyboardInterrupt:
        print("[AIGATE] stopped by user", file=sys.stderr)