import os
import sys
import time
import json
from tools.capital_client import CapitalClient

def load_symbols_epics(txt_file="all_epics.txt"):
    symbols = []
    with open(txt_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("-->"): continue
            parts = line.split("\t")
            if len(parts) >= 1:
                symbols.append(parts[0])
    return symbols

def fetch_full_history(symbol, timeframe="HOUR", days=730):
    client = CapitalClient()
    epic = symbol  # Oletetaan EPIC=symboli, muokkaa jos mapping on eri!
    print(f"[FETCH] {symbol} ({epic}) {timeframe}")
    end = int(time.time() * 1000)
    start = end - days * 86400 * 1000
    all_candles = []
    fail_count = 0
    while True:
        try:
            candles = client.get_candles(epic, resolution=timeframe, max=200, from_ts=start, to_ts=end)
            if not candles:
                print("[INFO] Ei lisää dataa, break")
                break
            all_candles.extend(candles)
            last_time = candles[-1].get('snapshotTime') or candles[-1].get('snapshotTimeUTC')
            if not last_time or last_time >= end:
                break
            start = last_time + 1
            time.sleep(0.25)
            fail_count = 0
        except Exception as e:
            print(f"[WARN] API error: {e} (backoff 10s)")
            time.sleep(10)
            fail_count += 1
            if fail_count >= 5:
                print("[FAIL] Liian monta virhettä, keskeytetään.")
                break
    print(f"[OK] {symbol}: {len(all_candles)} candles")
    os.makedirs("data/capital", exist_ok=True)
    out_path = f"data/capital/{symbol}_{timeframe}.json"
    meta = {
        "symbol": symbol,
        "epic": epic,
        "timeframe": timeframe,
        "utc": True,
        "rows": len(all_candles),
        "source": "capital.com",
    }
    with open(out_path, "w") as f:
        json.dump({"meta": meta, "candles": all_candles}, f)
    print(f"[SAVE] {out_path}")

if __name__ == "__main__":
    SYMBOLS = load_symbols_epics("all_epics.txt")
    TIMEFRAMES = ["MINUTE_15", "HOUR", "HOUR_4"]
    DAYS_MAP = {"MINUTE_15": 365, "HOUR": 730, "HOUR_4": 1095}
    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            days = DAYS_MAP[tf]
            fetch_full_history(symbol, tf, days)
