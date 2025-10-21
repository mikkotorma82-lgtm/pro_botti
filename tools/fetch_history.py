import os
from dotenv import load_dotenv
import requests
import pandas as pd
from datetime import datetime, timedelta

load_dotenv("/root/pro_botti/secrets.env", override=True)

CAPITAL_API_KEY = os.getenv("CAPITAL_API_KEY")
CAPITAL_API_BASE = os.getenv("CAPITAL_API_BASE", "https://api-capital.backend-capital.com")
CAPITAL_USERNAME = os.getenv("CAPITAL_USERNAME")
CAPITAL_PASSWORD = os.getenv("CAPITAL_PASSWORD")

def get_session_tokens():
    url = f"{CAPITAL_API_BASE}/api/v1/session"
    payload = {"identifier": CAPITAL_USERNAME, "password": CAPITAL_PASSWORD}
    headers = {"X-CAP-API-KEY": CAPITAL_API_KEY, "Content-Type": "application/json"}
    resp = requests.post(url, json=payload, headers=headers)
    cst = resp.headers.get("CST") or resp.headers.get("cst")
    xsec = resp.headers.get("X-SECURITY-TOKEN") or resp.headers.get("x-security-token")
    if not cst or not xsec:
        print("Login response:", resp.text)
        raise Exception(f"API login failed, CST or X-SECURITY-TOKEN missing. Got headers: {resp.headers}")
    return cst, xsec

def fetch_history(symbol, resolution, start, end):
    cst, xsec = get_session_tokens()
    url = f"{CAPITAL_API_BASE}/api/v1/prices/{symbol}"
    dfs = []
    next_dt = start
    tf_map = {"MINUTE": timedelta(minutes=1), "MINUTE_5": timedelta(minutes=5), "HOUR": timedelta(hours=1), "DAY": timedelta(days=1)}
    step = tf_map.get(resolution, timedelta(hours=1))
    while next_dt < end:
        params = {
            "resolution": resolution,
            "max": 200,
            "from": int(next_dt.timestamp() * 1000),
            "to": int(min(end.timestamp(), next_dt.timestamp() + 200 * step.total_seconds()) * 1000)
        }
        headers = {
            "X-CAP-API-KEY": CAPITAL_API_KEY,
            "CST": cst,
            "X-SECURITY-TOKEN": xsec
        }
        r = requests.get(url, params=params, headers=headers)
        print("Request URL:", r.url)
        print("Status code:", r.status_code)
        print("Response:", r.text)
        if r.status_code in [401, 403]:
            print("Session expired, re-login...")
            cst, xsec = get_session_tokens()
            headers["CST"] = cst
            headers["X-SECURITY-TOKEN"] = xsec
            r = requests.get(url, params=params, headers=headers)
            print("Request URL:", r.url)
            print("Status code:", r.status_code)
            print("Response:", r.text)
        r.raise_for_status()
        data = r.json()
        prices = data.get("prices", [])
        if not prices:
            print("No more data, breaking.")
            break
        d = pd.DataFrame(prices)
        dfs.append(d)
        next_dt = datetime.fromisoformat(d["snapshotTime"].iloc[-1]) + step
        print(f"Fetched {len(d)} rows up to {next_dt}")
    if not dfs:
        raise Exception("No data fetched from Capital API!")
    df = pd.concat(dfs).reset_index(drop=True)
    return df

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 5:
        print("Usage: python tools/fetch_history.py SYMBOL RESOLUTION START END")
        print("Example: python tools/fetch_history.py US500 HOUR 2022-01-01 2023-01-01")
        exit(1)
    symbol = sys.argv[1]
    resolution = sys.argv[2]
    start = datetime.strptime(sys.argv[3], "%Y-%m-%d")
    end = datetime.strptime(sys.argv[4], "%Y-%m-%d")
    df = fetch_history(symbol, resolution, start, end)
    out_path = f"data/{symbol}_{resolution}_{start.date()}_{end.date()}.csv"
    df.to_csv(out_path, index=False)
    print(f"Saved {len(df)} rows to {out_path}")
