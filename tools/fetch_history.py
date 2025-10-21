import requests
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Lataa secrets.env
load_dotenv("/root/pro_botti/secrets.env")

CAPITAL_API_KEY = os.getenv("CAPITAL_API_KEY")
CAPITAL_API_BASE = os.getenv("CAPITAL_API_BASE", "https://api-capital.backend-capital.com")
CAPITAL_USERNAME = os.getenv("CAPITAL_USERNAME")
CAPITAL_PASSWORD = os.getenv("CAPITAL_PASSWORD")

def get_session_tokens():
    url = f"{CAPITAL_API_BASE}/api/v1/session"
    payload = {
        "identifier": CAPITAL_USERNAME,
        "password": CAPITAL_PASSWORD
    }
    headers = {
        "X-CAP-API-KEY": CAPITAL_API_KEY,
        "Content-Type": "application/json"
    }
    resp = requests.post(url, json=payload, headers=headers)
    cst = resp.headers.get("CST")
    xsec = resp.headers.get("X-SECURITY-TOKEN")
    if not cst or not xsec:
        raise Exception(f"API login failed, CST or X-SECURITY-TOKEN missing. Got headers: {resp.headers}")
    return cst, xsec

def fetch_history(symbol, resolution, start, end):
    # start, end: datetime-objekteja
    cst, xsec = get_session_tokens()
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
        if r.status_code == 403 or r.status_code == 401:
            # Session vanhentunut, kirjaudu uudelleen
            print("Session expired, re-login...")
            cst, xsec = get_session_tokens()
            headers["CST"] = cst
            headers["X-SECURITY-TOKEN"] = xsec
            r = requests.get(url, params=params, headers=headers)
        r.raise_for_status()
        data = r.json()
        prices = data.get("prices", [])
        if not prices:
            break
        import pandas as pd
        d = pd.DataFrame(prices)
        dfs.append(d)
        next_dt = datetime.fromtimestamp(d["snapshotTime"].iloc[-1]/1000) + timedelta(minutes=1)
        print(f"Fetched {len(d)} rows up to {next_dt}")
    if not dfs:
        raise Exception("No data fetched from Capital API!")
    df = pd.concat(dfs).reset_index(drop=True)
    return df

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 5:
        print("Usage: python fetch_capital_history.py SYMBOL RESOLUTION START END")
        print("Example: python fetch_capital_history.py US500 HOUR 2022-01-01 2023-01-01")
        exit(1)
    symbol = sys.argv[1]
    resolution = sys.argv[2]  # esim. MINUTE, HOUR, DAY
    start = datetime.strptime(sys.argv[3], "%Y-%m-%d")
    end = datetime.strptime(sys.argv[4], "%Y-%m-%d")
    df = fetch_history(symbol, resolution, start, end)
    out_path = f"data/{symbol}_{resolution}_{start.date()}_{end.date()}.csv"
    df.to_csv(out_path, index=False)
    print(f"Saved {len(df)} rows to {out_path}")
