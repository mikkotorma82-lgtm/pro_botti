import os, time, sys, traceback, json
from pathlib import Path
from tools.live_daemon import get_bid_ask
from tools import trade_live

try:
    from tools import order_router as router
except Exception:
    router = None

try:
    from utils.position_watcher import create_position_watcher
    POSITION_WATCHER_AVAILABLE = True
except Exception:
    POSITION_WATCHER_AVAILABLE = False

LOOP_SEC = float(os.getenv("LOOP_SEC", "5"))
ALWAYS_MANAGE_OPEN = os.getenv("ALWAYS_MANAGE_OPEN_POSITIONS", "1") == "1"

# Load symbols from active_symbols.json or fallback to env
def load_trading_symbols():
    """Load symbols from state/active_symbols.json or fallback to env."""
    ROOT = Path(__file__).parent.parent
    active_file = ROOT / "state" / "active_symbols.json"
    
    if active_file.exists():
        try:
            data = json.loads(active_file.read_text())
            symbols = data.get("symbols", [])
            if symbols:
                print(f"[CONFIG] Loaded {len(symbols)} active symbols from {active_file}")
                print(f"[CONFIG] Active symbols: {symbols}")
                return symbols
        except Exception as e:
            print(f"[CONFIG] Failed to load {active_file}: {e}")
    
    # Fallback to env
    symbols = [s.strip().upper() for s in os.getenv("TRADE_SYMBOLS","").split(",") if s.strip()]
    if not symbols:
        symbols = ["BTCUSDT","ETHUSDT","US500","US100","DE40","UK100","JP225"]
    print(f"[CONFIG] Using fallback symbols from env: {symbols}")
    return symbols

SYMBOLS = load_trading_symbols()

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
    print(f"[CONFIG] Position watcher: {'enabled' if POSITION_WATCHER_AVAILABLE and ALWAYS_MANAGE_OPEN else 'disabled'}")
    
    # Initialize position watcher if available
    position_watcher = None
    if POSITION_WATCHER_AVAILABLE and ALWAYS_MANAGE_OPEN:
        try:
            # Create a mock broker for position watcher
            # In production, replace this with actual broker instance
            class MockBroker:
                def open_positions(self):
                    return []  # Would query real broker
                def close_position(self, **kwargs):
                    print(f"[WATCHER] Would close position: {kwargs}")
            
            position_watcher = create_position_watcher(
                MockBroker(),
                check_interval=30,
                guard_config={}
            )
            print("[CONFIG] Position watcher initialized")
        except Exception as e:
            print(f"[CONFIG] Failed to initialize position watcher: {e}")
    
    while True:
        t0 = time.time()
        
        # Check and manage positions if enabled
        if position_watcher and position_watcher.should_check():
            try:
                result = position_watcher.check_and_manage_positions(SYMBOLS)
                if result.get("open_count", 0) > 0:
                    print(f"[WATCHER] Managed {result['managed']} positions")
            except Exception as e:
                print(f"[WATCHER] Error: {e}")
        
        # Trade active symbols
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
