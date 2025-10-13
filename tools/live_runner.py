import os, time, sys, traceback
from tools.live_daemon import get_bid_ask
from tools import trade_live

try:
    from tools import order_router as router
except Exception:
    router = None

LOOP_SEC = float(os.getenv("LOOP_SEC", "5"))
SYMBOLS = [s.strip().upper() for s in os.getenv("TRADE_SYMBOLS","").split(",") if s.strip()]
if not SYMBOLS:
    SYMBOLS = ["BTCUSDT","ETHUSDT","US500","US100","DE40","UK100","JP225"]

EXECUTE = (os.getenv("EXECUTE_ORDERS","0") == "1" and os.getenv("ORDER_ENABLE","0") == "1")
PLACE_ON_SIGNAL = os.getenv("PLACE_ON_SIGNAL","0") == "1"
DRY_RUN = os.getenv("DRY_RUN","1") == "1"
FIXED_QTY = float(os.getenv("FIXED_QTY", "1"))

def decide_side(scores: dict) -> str | None:
    p_long = float(scores.get("long", 0.5))
    p_short = float(scores.get("short", 0.5))
    # peruskynnykset
    if p_long >= 0.58 and p_long > p_short: return "BUY"
    if p_short >= 0.58 and p_short > p_long: return "SELL"
    return None

def place_order(symbol: str, side: str, qty: float):
    if DRY_RUN or not EXECUTE or not PLACE_ON_SIGNAL:
        print(f"[ORDER] {symbol} {side} qty={qty} resp={{'dry_run': True, 'exchange':'capital'}}")
        return
    if router and hasattr(router, "create_market_order"):
        try:
            resp = router.create_market_order(symbol, side, qty)
            print(f"[ORDER] {symbol} {side} qty={qty} resp={resp}")
        except Exception as e:
            print(f"[ERR] order {symbol}: {e}")
            traceback.print_exc()
    else:
        print(f"[ORDER] {symbol} {side} qty={qty} resp={{'warn':'router missing'}}")

def main():
    print(f"[AIGATE] start symbols={SYMBOLS} EXECUTE={EXECUTE} DRY_RUN={DRY_RUN} PLACE_ON_SIGNAL={PLACE_ON_SIGNAL}")
    while True:
        t0 = time.time()
        for sym in SYMBOLS:
            try:
                ba = get_bid_ask(sym)
                if isinstance(ba, tuple) and len(ba)==2 and all(x is not None for x in ba):
                    bid, ask = ba
                    if isinstance(bid, (int,float)) and isinstance(ask, (int,float)):
                        print(f"[PRICE] {sym} {bid}/{ask}")
                else:
                    print(f"[PRICE] {sym} (unavailable)")

                # signaali
                try:
                    scores = trade_live.get_scores(sym)
                except Exception:
                    scores = {}
                print(f"[SIG] {sym} scores={scores}")
                side = decide_side(scores)
                print(f"[SIG] {sym} side={side}")

                if side:
                    place_order(sym, side, FIXED_QTY)
            except Exception as e:
                print(f"[ERR] loop {sym}: {e}")
                traceback.print_exc()

        dt = time.time() - t0
        time.sleep(max(0.1, LOOP_SEC - dt))

if __name__ == "__main__":
    main()
