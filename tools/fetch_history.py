import os
import sys
import time
import json
from tools.capital_client import CapitalClient

client = CapitalClient()

def find_epic(symbol):
    """Hakee Capital.com API:sta oikean EPIC-koodin symbolille"""
    url = f"{client.base}/api/v1/markets"
    r = client.session.get(url, params={"searchTerm": symbol})
    if r.status_code != 200:
        print(f"[WARN] Epic-haku epäonnistui {symbol}: {r.status_code}")
        return None
    data = r.json().get("markets", [])
    if not data:
        print(f"[WARN] Epic puuttuu {symbol}")
        return None
    epic = data[0]["epic"]
    print(f"[EPIC] {symbol} -> {epic}")
    return epic

def fetch_full_history(symbol, timeframe="HOUR", days=730):
    epic = find_epic(symbol)
    if not epic:
        print(f"[SKIP] Ei epicciä {symbol}")
        return
    print(f"[FETCH] {symbol} ({epic}) {timeframe}")
    end = int(time.time() * 1000)
    start = end - days * 86400 * 1000
    all_candles = []
    while True:
        candles = client.get_candles(epic, resolution=timeframe, max=200, from_ts=start, to_ts=end)
        if not candles:
            break
        all_candles.extend(candles)
        last_time = candles[-1]['snapshotTime']
        if last_time >= end:
            break
        start = last_time + 1
        time.sleep(0.25)
    print(f"[OK] {symbol}: {len(all_candles)} candles")
    os.makedirs("data/capital", exist_ok=True)
    out_path = f"data/capital/{symbol}_{timeframe}.json"
    with open(out_path, "w") as f:
        json.dump(all_candles, f)
    print(f"[SAVE] {out_path}")

if __name__ == "__main__":
    # Esimerkki: fetch_full_history("US500", "HOUR", 730)
    for symbol in ["US500", "BTCUSD", "AAPL"]:  # lisää haluamasi symbolit
        fetch_full_history(symbol, "HOUR", 730)
