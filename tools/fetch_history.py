import requests
import pandas as pd
import os
from datetime import datetime, timedelta

CAPITAL_API_KEY = os.getenv("CAPITAL_API_KEY")
CAPITAL_API_BASE = os.getenv("CAPITAL_API_BASE", "https://api-capital.backend-capital.com")
CAPITAL_USERNAME = os.getenv("CAPITAL_USERNAME")
CAPITAL_PASSWORD = os.getenv("CAPITAL_PASSWORD")

def get_cst_xsec():
    url = f"{CAPITAL_API_BASE}/api/v1/session"
    headers = {"X-CAP-API-KEY": CAPITAL_API_KEY, "Content-Type": "application/json"}
    data = {"identifier": CAPITAL_USERNAME, "password": CAPITAL_PASSWORD}
    r = requests.post(url, headers=headers, json=data)
    cst = r.headers.get("CST")
    xsec = r.headers.get("X-SECURITY-TOKEN")
    if not cst or not xsec:
        raise Exception("Capital login failed: CST or XSEC missing")
    return cst, xsec

def fetch_history(symbol, resolution, start, end):
    cst, xsec = get_cst_xsec()
    url = f"{CAPITAL_API_BASE}/api/v1/prices/{symbol}"
    dfs = []
    next_dt = start
    while next_dt < end:
        params = {
            "resolution": resolution,
            "max": 200,
            "from": int(next_dt.timestamp() * 1000),
            "to": int(min(end.timestamp(), next_dt.timestamp() + 200 * 60) * 1000)
        }
        headers = {
            "X-CAP-API-KEY": CAPITAL_API_KEY,
            "CST": cst,
            "X-SECURITY-TOKEN": xsec
        }
        r = requests.get(url, params=params, headers=headers)
        r.raise_for_status()
        data = r.json()
        prices = data.get("prices", [])
        if not prices:
            break
        d = pd.DataFrame(prices)
        dfs.append(d)
        # Move to next batch
        next_dt = datetime.fromtimestamp(d["snapshotTime"].iloc[-1]/1000) + timedelta(minutes=1)
        print(f"Fetched {len(d)} rows up to {next_dt}")
    if not dfs:
        raise Exception("No data fetched from Capital API!")
    df = pd.concat(dfs).reset_index(drop=True)
    return df

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 5:
        print("Usage: python fetch_history.py SYMBOL RESOLUTION START END")
        print("Example: python fetch_history.py US500 MINUTE 2020-01-01 2025-01-01")
        exit(1)
    symbol = sys.argv[1]
    resolution = sys.argv[2]
    start = datetime.strptime(sys.argv[3], "%Y-%m-%d")
    end = datetime.strptime(sys.argv[4], "%Y-%m-%d")
    df = fetch_history(symbol, resolution, start, end)
    out_path = f"data/{symbol}_{resolution}_{start.date()}_{end.date()}.csv"
    df.to_csv(out_path, index=False)
    print(f"Saved {len(df)} rows to {out_path}")
